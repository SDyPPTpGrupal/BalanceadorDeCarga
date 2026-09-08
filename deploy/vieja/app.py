"""Servidor gRPC minimo para probar la conmutacion del balanceador."""

import argparse
from concurrent import futures

import grpc

import contrato_pb2
import contrato_pb2_grpc


class TestService(contrato_pb2_grpc.ServicioServicer):
    def Identidad(self, request, context):
        return contrato_pb2.Instancia()

    def Salud(self, request, context):
        return contrato_pb2.EstadoSalud(status=contrato_pb2.EstadoSalud.SANO)

    def Echo(self, request, context):
        return contrato_pb2.PongRespuesta()

    def ListarPersonas(self, request, context):
        return contrato_pb2.ListaPersonas()

    def CrearPersona(self, request, context):
        return contrato_pb2.RespuestaPersona()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    contrato_pb2_grpc.add_ServicioServicer_to_server(TestService(), server)
    server.add_insecure_port(f"0.0.0.0:{args.port}")
    server.start()
    print(f"Python gRPC de prueba escuchando en {args.port}", flush=True)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    main()
