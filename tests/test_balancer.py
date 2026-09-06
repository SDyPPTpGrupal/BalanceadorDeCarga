import json
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
        balancer.current_backend = balancer.OLD_BACKEND_URL
        cls.proxy_server = balancer.create_grpc_server()
        cls.proxy_server.start()
        cls.control_server = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
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
        cls.proxy_server.stop(0)
        cls.python_server.stop(0)
        cls.java_server.stop(0)

    def setUp(self):
        self.channel = grpc.insecure_channel(f"127.0.0.1:{self.balancer_port}")
        self.stub = contrato_pb2_grpc.ServicioStub(self.channel)

    def tearDown(self):
        self.channel.close()

    def switch_to(self, version):
        connection = HTTPConnection("127.0.0.1", self.control_port)
        body = json.dumps({"version": version})
        connection.request(
            "POST",
            "/__switch",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        self.assertEqual(response.status, 200, payload)

    def test_python_backend_handles_all_contract_operations(self):
        identidad = self.stub.Identidad(contrato_pb2.IdentidadPedido())
        self.assertEqual(identidad.app, "python")
        self.assertEqual(self.stub.Salud(contrato_pb2.SaludPedido()).app, "python")
        self.assertEqual(self.stub.Echo(contrato_pb2.PingPedido(ping="hola")).servido_por, "python")
        self.assertEqual(
            self.stub.ListarPersonas(contrato_pb2.ListarPersonasPedido()).personas[0].nombre,
            "Ada Lovelace",
        )
        created = self.stub.CrearPersona(contrato_pb2.NuevaPersona(nombre="Grace", legajo=100201))
        self.assertEqual(created.servido_por, "python")

    def test_switch_to_java_mock_without_restarting_balancer(self):
        self.switch_to("nueva")
        self.assertEqual(self.stub.Identidad(contrato_pb2.IdentidadPedido()).app, "java")
        self.assertEqual(self.stub.Echo(contrato_pb2.PingPedido(ping="hola")).servido_por, "java")
        self.switch_to("vieja")
        self.assertEqual(self.stub.Identidad(contrato_pb2.IdentidadPedido()).app, "python")


if __name__ == "__main__":
    unittest.main()