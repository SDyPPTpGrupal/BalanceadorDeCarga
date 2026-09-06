"""Servidor balanceador gRPC blue-green para backends locales."""

import http.server
import json
import logging
import os
import threading
from concurrent import futures
from urllib.parse import urlsplit

import grpc

import contrato_pb2
import contrato_pb2_grpc


PORT = int(os.environ.get("PORT", 80))
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", 8088))
OLD_BACKEND_URL = os.environ.get("OLD_BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
NEW_BACKEND_URL = os.environ.get("NEW_BACKEND_URL", "http://127.0.0.1:8081").rstrip("/")
BACKEND_URL = os.environ.get("BACKEND_URL", OLD_BACKEND_URL).rstrip("/")
LOG_FILE = os.environ.get("BALANCER_LOG", "balancer.log")

backend_lock = threading.Lock()
current_backend = BACKEND_URL

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


def get_backend():
    with backend_lock:
        return current_backend


def check_backend(backend):
    channel = grpc.insecure_channel(backend_target(backend))
    try:
        stub = contrato_pb2_grpc.ServicioStub(channel)
        response = stub.Salud(contrato_pb2.SaludPedido(), timeout=3)
        return response.status == contrato_pb2.EstadoSalud.SANO
    finally:
        channel.close()


class ProxyServicer:
    def __getattr__(self, method_name):
        if method_name not in RPC_TYPES:
            raise AttributeError(method_name)

        def forward(request, context):
            backend = get_backend()
            channel = grpc.insecure_channel(backend_target(backend))
            try:
                stub = contrato_pb2_grpc.ServicioStub(channel)
                response = getattr(stub, method_name)(request, timeout=10)
                logging.info("%s -> %s status=OK", method_name, backend)
                return response
            except grpc.RpcError as exc:
                logging.error(
                    "%s -> %s status=%s error=%s",
                    method_name,
                    backend,
                    exc.code().name,
                    exc.details(),
                )
                context.abort(exc.code(), exc.details())
            finally:
                channel.close()

        return forward


def create_grpc_server():
    servicer = ProxyServicer()
    handlers = {}
    for method_name, (request_type, response_type) in RPC_TYPES.items():
        handlers[method_name] = grpc.unary_unary_rpc_method_handler(
            getattr(servicer, method_name),
            request_deserializer=request_type.FromString,
            response_serializer=response_type.SerializeToString,
        )
    generic_handler = grpc.method_handlers_generic_handler("sdypp.Servicio", handlers)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_insecure_port(f"[::]:{PORT}")
    return server


class ControlHandler(http.server.BaseHTTPRequestHandler):
    """Control local opcional; no forma parte del servicio gRPC público."""

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
            self.send_json(200, {"backend": get_backend()})
            return
        self.send_json(404, {"error": "ruta no encontrada"})

    def do_POST(self):
        global current_backend

        if self.path != "/__switch":
            self.send_json(404, {"error": "ruta no encontrada"})
            return
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

        try:
            if not check_backend(backend):
                raise OSError("Salud no devolvió SANO")
        except (OSError, grpc.RpcError) as exc:
            logging.warning("switch rechazado backend=%s error=%s", backend, exc)
            self.send_json(503, {"error": "backend no saludable", "backend": backend})
            return

        with backend_lock:
            previous = current_backend
            current_backend = backend
        logging.info("switch -> %s status=OK previous=%s", backend, previous)
        self.send_json(200, {"status": "switched", "backend": backend, "previous": previous})

    def log_message(self, format, *args):
        return


def run():
    grpc_server = create_grpc_server()
    control_server = http.server.ThreadingHTTPServer(("127.0.0.1", CONTROL_PORT), ControlHandler)
    threading.Thread(target=control_server.serve_forever, daemon=True).start()
    grpc_server.start()
    print(
        f"[*] Balanceador gRPC en {PORT}, backend {current_backend}; control local en {CONTROL_PORT}",
        flush=True,
    )
    try:
        grpc_server.wait_for_termination()
    except KeyboardInterrupt:
        grpc_server.stop(0)
        control_server.shutdown()


if __name__ == "__main__":
    run()
