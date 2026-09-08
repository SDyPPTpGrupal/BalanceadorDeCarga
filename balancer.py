"""Balanceador HTTP con backends internos gRPC."""

import http.server
import json
import logging
import os
import threading
from urllib.parse import urlsplit

import grpc
from google.protobuf.json_format import MessageToDict, ParseDict

import contrato_pb2
import contrato_pb2_grpc


PORT = int(os.environ.get("PORT", 80))
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", 8088))
OLD_BACKEND_URL = os.environ.get("OLD_BACKEND_URL", "http://host.docker.internal:9001").rstrip("/")
NEW_BACKEND_URL = os.environ.get("NEW_BACKEND_URL", "http://host.docker.internal:9002").rstrip("/")
BACKENDS = os.environ.get("BACKENDS", f"{OLD_BACKEND_URL},{NEW_BACKEND_URL}")
HEALTH_CHECK_INTERVAL = float(os.environ.get("HEALTH_CHECK_INTERVAL", "5"))
LOG_FILE = os.environ.get("BALANCER_LOG", "balancer.log")

backend_lock = threading.Lock()
backends = [backend.strip().rstrip("/") for backend in BACKENDS.split(",") if backend.strip()]
healthy_backends = set()
next_backend = 0
forced_backend = OLD_BACKEND_URL
previous_backend = None

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | balancer | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

RPC_TYPES = {
    "Identidad": (contrato_pb2.IdentidadPedido, contrato_pb2.Instancia),
    "Salud": (contrato_pb2.SaludPedido, contrato_pb2.EstadoSalud),
    "Echo": (contrato_pb2.PingPedido, contrato_pb2.PongRespuesta),
    "ListarPersonas": (contrato_pb2.ListarPersonasPedido, contrato_pb2.ListaPersonas),
    "CrearPersona": (contrato_pb2.NuevaPersona, contrato_pb2.RespuestaPersona),
}


def backend_target(backend):
    parsed = urlsplit(backend)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("backend debe ser una URL HTTP válida")
    return parsed.netloc


def get_next_backend():
    global next_backend

    with backend_lock:
        if forced_backend:
            if forced_backend not in healthy_backends:
                raise BackendUnavailable("el backend activo no está saludable")
            return forced_backend

        available = [backend for backend in backends if backend in healthy_backends]
        if not available:
            raise BackendUnavailable("no hay backends saludables")
        backend = available[next_backend % len(available)]
        next_backend = (next_backend + 1) % len(available)
        return backend


class BackendUnavailable(Exception):
    pass


def grpc_status_http_code(code):
    return {
        grpc.StatusCode.INVALID_ARGUMENT: 400,
        grpc.StatusCode.NOT_FOUND: 404,
        grpc.StatusCode.ALREADY_EXISTS: 409,
        grpc.StatusCode.UNAVAILABLE: 503,
        grpc.StatusCode.DEADLINE_EXCEEDED: 504,
    }.get(code, 502)


def check_backend(backend):
    channel = grpc.insecure_channel(backend_target(backend))
    try:
        stub = contrato_pb2_grpc.ServicioStub(channel)
        response = stub.Salud(contrato_pb2.SaludPedido(), timeout=3)
        return response.status == contrato_pb2.EstadoSalud.SANO
    except grpc.RpcError:
        return False
    finally:
        channel.close()


def refresh_health():
    healthy = {backend for backend in backends if check_backend(backend)}
    with backend_lock:
        healthy_backends.clear()
        healthy_backends.update(healthy)
    return healthy


def health_monitor():
    while True:
        refresh_health()
        threading.Event().wait(HEALTH_CHECK_INTERVAL)


def call_backend(method_name, request):
    backend = get_next_backend()
    channel = grpc.insecure_channel(backend_target(backend))
    try:
        stub = contrato_pb2_grpc.ServicioStub(channel)
        response = getattr(stub, method_name)(request, timeout=10)
        return response, backend
    except grpc.RpcError as exc:
        if exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
            with backend_lock:
                healthy_backends.discard(backend)
        logging.error(
            "%s -> %s status=%s error=%s",
            method_name,
            backend,
            exc.code().name,
            exc.details(),
        )
        raise
    finally:
        channel.close()


def response_json(response):
    return MessageToDict(response, preserving_proto_field_name=True)


class PublicHandler(http.server.BaseHTTPRequestHandler):
    """API HTTP pública; los backends se consultan exclusivamente por gRPC."""

    routes = {
        ("GET", "/"): ("Identidad", contrato_pb2.IdentidadPedido),
        ("GET", "/health"): ("Salud", contrato_pb2.SaludPedido),
        ("GET", "/personas"): ("ListarPersonas", contrato_pb2.ListarPersonasPedido),
        ("POST", "/echo"): ("Echo", contrato_pb2.PingPedido),
        ("POST", "/personas"): ("CrearPersona", contrato_pb2.NuevaPersona),
    }

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def handle_route(self, method):
        route = urlsplit(self.path).path
        route_info = self.routes.get((method, route))
        if route_info is None:
            self.send_json(404, {"error": "ruta no encontrada"})
            return

        method_name, request_type = route_info
        try:
            payload = self.read_json() if method == "POST" else {}
            request = ParseDict(payload, request_type())
            response, backend = call_backend(method_name, request)
            status = 201 if method == "POST" and route == "/personas" else 200
            logging.info("%s %s -> %s status=%s", method, route, backend, status)
            self.send_json(status, response_json(response))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self.send_json(400, {"error": str(exc)})
        except grpc.RpcError as exc:
            self.send_json(
                grpc_status_http_code(exc.code()),
                {"error": exc.details() or exc.code().name},
            )
        except BackendUnavailable as exc:
            self.send_json(503, {"error": str(exc)})

    def do_GET(self):
        self.handle_route("GET")

    def do_POST(self):
        self.handle_route("POST")

    def log_message(self, format, *args):
        return


class ControlHandler(http.server.BaseHTTPRequestHandler):
    """Control local opcional; no forma parte de la API HTTP pública."""

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/__status":
            with backend_lock:
                status = {
                    "backends": backends,
                    "healthy": sorted(healthy_backends),
                    "mode": "blue-green" if forced_backend else "round-robin",
                    "active": forced_backend,
                }
            self.send_json(200, status)
            return
        self.send_json(404, {"error": "ruta no encontrada"})

    def do_POST(self):
        global forced_backend, previous_backend

        if self.path not in ("/__switch", "/__rollback", "/__pool"):
            self.send_json(404, {"error": "ruta no encontrada"})
            return

        if self.path == "/__pool":
            with backend_lock:
                previous_backend = forced_backend
                forced_backend = None
            self.send_json(200, {"status": "round-robin", "previous": previous_backend})
            return

        if self.path == "/__rollback":
            with backend_lock:
                target = previous_backend
            if not target:
                self.send_json(409, {"error": "no hay backend anterior para rollback"})
                return
        else:
            try:
                payload = self.read_json()
                backend = str(payload.get("backend", "")).rstrip("/")
                if not backend:
                    version = str(payload["version"]).lower()
                    backend = {"vieja": OLD_BACKEND_URL, "nueva": NEW_BACKEND_URL}[version]
                backend_target(backend)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self.send_json(400, {"error": str(exc)})
                return
            target = backend

        if not check_backend(target):
            self.send_json(503, {"error": "backend no saludable", "backend": target})
            return

        with backend_lock:
            previous = forced_backend
            previous_backend = previous
            forced_backend = target
            healthy_backends.add(target)
        logging.info("switch -> %s status=OK previous=%s", target, previous)
        self.send_json(200, {"status": "switched", "backend": target, "previous": previous})

    def log_message(self, format, *args):
        return


def run():
    refresh_health()
    public_server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), PublicHandler)
    control_server = http.server.ThreadingHTTPServer(("127.0.0.1", CONTROL_PORT), ControlHandler)
    threading.Thread(target=control_server.serve_forever, daemon=True).start()
    threading.Thread(target=public_server.serve_forever, daemon=True).start()
    threading.Thread(target=health_monitor, daemon=True).start()
    print(
        f"[*] Balanceador HTTP en {PORT}, backends gRPC {backends}; control local en {CONTROL_PORT}",
        flush=True,
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        public_server.shutdown()
        control_server.shutdown()


if __name__ == "__main__":
    run()
