package local.test;

import ar.edu.unlu.sdypp.contrato.EstadoSalud;
import ar.edu.unlu.sdypp.contrato.IdentidadPedido;
import ar.edu.unlu.sdypp.contrato.Instancia;
import ar.edu.unlu.sdypp.contrato.ListaPersonas;
import ar.edu.unlu.sdypp.contrato.ListarPersonasPedido;
import ar.edu.unlu.sdypp.contrato.NuevaPersona;
import ar.edu.unlu.sdypp.contrato.PingPedido;
import ar.edu.unlu.sdypp.contrato.PongRespuesta;
import ar.edu.unlu.sdypp.contrato.RespuestaPersona;
import ar.edu.unlu.sdypp.contrato.SaludPedido;
import ar.edu.unlu.sdypp.contrato.ServicioGrpc;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;

public final class TestServer {
    private static final class Service extends ServicioGrpc.ServicioImplBase {
        @Override
        public void identidad(IdentidadPedido request, StreamObserver<Instancia> responseObserver) {
            responseObserver.onNext(Instancia.getDefaultInstance());
            responseObserver.onCompleted();
        }

        @Override
        public void salud(SaludPedido request, StreamObserver<EstadoSalud> responseObserver) {
            responseObserver.onNext(EstadoSalud.newBuilder()
                .setStatus(EstadoSalud.Estado.SANO)
                    .build());
            responseObserver.onCompleted();
        }

        @Override
        public void echo(PingPedido request, StreamObserver<PongRespuesta> responseObserver) {
            responseObserver.onNext(PongRespuesta.getDefaultInstance());
            responseObserver.onCompleted();
        }

        @Override
        public void listarPersonas(ListarPersonasPedido request, StreamObserver<ListaPersonas> responseObserver) {
            responseObserver.onNext(ListaPersonas.getDefaultInstance());
            responseObserver.onCompleted();
        }

        @Override
        public void crearPersona(NuevaPersona request, StreamObserver<RespuestaPersona> responseObserver) {
            responseObserver.onNext(RespuestaPersona.getDefaultInstance());
            responseObserver.onCompleted();
        }
    }

    public static void main(String[] args) throws Exception {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 9002;
        Server server = ServerBuilder.forPort(port).addService(new Service()).build().start();
        System.out.println("Java gRPC de prueba escuchando en " + port);
        Runtime.getRuntime().addShutdownHook(new Thread(server::shutdown));
        server.awaitTermination();
    }
}
