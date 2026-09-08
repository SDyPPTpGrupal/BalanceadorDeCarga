import json
import http.server
import threading
import unittest
from concurrent import futures
from http.client import HTTPConnection

import grpc

import balancer
import contrato_pb2
import contrato_pb2_grpc


class MockServicio(contrato_pb2_grpc.ServicioServicer):
    def __init__(self, app, version):
        self.app = app
        self.version = version

    def Identidad(self, request, context):
        return contrato_pb2.Instancia(
            app=self.app,
            lenguaje=self.app,
            version=self.version,
            mensaje=f"mock {self.app}",
            host="localhost",
        )

    def Salud(self, request, context):
        return contrato_pb2.EstadoSalud(
            status=contrato_pb2.EstadoSalud.SANO,
            app=self.app,
            version=self.version,
        )

    def Echo(self, request, context):
        return contrato_pb2.PongRespuesta(
            pong=request.ping,
            servido_por=self.app,
            version=self.version,
        )

    def ListarPersonas(self, request, context):
        return contrato_pb2.ListaPersonas(
            servido_por=self.app,
            personas=[contrato_pb2.Persona(id=1, nombre="Ada Lovelace", legajo=100200)],
        )

    def CrearPersona(self, request, context):
        return contrato_pb2.RespuestaPersona(
            servido_por=self.app,
            persona=contrato_pb2.Persona(id=2, nombre=request.nombre, legajo=request.legajo),
        )


def start_mock(port, app, version):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    contrato_pb2_grpc.add_ServicioServicer_to_server(MockServicio(app, version), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    return server


class BalancerIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_port = 18080
        cls.new_port = 18081
        cls.control_port = 18088
        cls.balancer_port = 18000
        cls.python_server = start_mock(cls.old_port, "python", 1)
        cls.java_server = start_mock(cls.new_port, "java", 2)

        balancer.PORT = cls.balancer_port
        balancer.CONTROL_PORT = cls.control_port
        balancer.OLD_BACKEND_URL = f"http://127.0.0.1:{cls.old_port}"
        balancer.NEW_BACKEND_URL = f"http://127.0.0.1:{cls.new_port}"
        balancer.backends = [balancer.OLD_BACKEND_URL, balancer.NEW_BACKEND_URL]
        balancer.next_backend = 0
        cls.public_server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", cls.balancer_port), balancer.PublicHandler
        )
        cls.public_thread = threading.Thread(
            target=cls.public_server.serve_forever,
            daemon=True,
        )
        cls.public_thread.start()
        cls.control_server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", cls.control_port), balancer.ControlHandler
        )
        cls.control_thread = threading.Thread(
            target=cls.control_server.serve_forever,
            daemon=True,
        )
        cls.control_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.control_server.shutdown()
        cls.public_server.shutdown()
        cls.python_server.stop(0)
        cls.java_server.stop(0)

    def setUp(self):
        with balancer.backend_lock:
            balancer.next_backend = 0

    def request(self, method, path, payload=None):
        connection = HTTPConnection("127.0.0.1", self.balancer_port)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if body is not None:
            headers["Content-Length"] = str(len(body))
        connection.request(
            method,
            path,
            body=body,
            headers=headers,
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_http_api_forwards_all_contract_operations(self):
        status, identidad = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(identidad["app"], "python")

        status, salud = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(salud["app"], "java")

        status, echo = self.request("POST", "/echo", {"ping": "hola"})
        self.assertEqual(status, 200)
        self.assertEqual(echo["servido_por"], "python")

        status, personas = self.request("GET", "/personas")
        self.assertEqual(status, 200)
        self.assertEqual(
            personas["personas"][0]["nombre"],
            "Ada Lovelace",
        )

        status, created = self.request(
            "POST", "/personas", {"nombre": "Grace", "legajo": 100201}
        )
        self.assertEqual(status, 200)
        self.assertEqual(created["servido_por"], "python")

    def test_requests_alternate_between_python_and_java(self):
        first_status, first = self.request("GET", "/")
        second_status, second = self.request("GET", "/")
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 200)
        self.assertEqual([first["app"], second["app"]], ["python", "java"])


if __name__ == "__main__":
    unittest.main()