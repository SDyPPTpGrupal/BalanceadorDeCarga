FROM alpine:latest

# Evitar buffering en la salida estándar de Python para ver logs en tiempo real
ENV PYTHONUNBUFFERED=1

# Argumentos configurables para no quemar usuarios ni puertos en el código del Dockerfile
ARG APP_USER=balancer
ARG APP_GROUP=balancer
ARG PORT=80

# Variable de entorno de ejecución para el puerto del servicio
ENV PORT=${PORT}

# Instalar Python 3, pip, libcap (para permitir enlazar puertos bajos sin ser root) y curl para diagnóstico
RUN apk add --no-cache \
        python3 \
        py3-pip \
        openjdk17-jre \
        libcap \
        curl && \
    setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))

# Crear usuario y grupo no privilegiados configurables
RUN addgroup -S "${APP_GROUP}" && adduser -S -G "${APP_GROUP}" -h /app "${APP_USER}"

WORKDIR /app

# Instalar dependencias, incluido grpcio-tools para generar los stubs del proto
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages


RUN python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. contrato.proto



# Copiar el script del balanceador
COPY balancer.py ./

# Asignar permisos al usuario de la aplicación
RUN chown -R "${APP_USER}:${APP_GROUP}" /app

# Ejecutar como usuario no privilegiado
USER "${APP_USER}"

# Puerto interno parametrizado
EXPOSE ${PORT}

# Comando de inicio del balanceador casero
CMD ["python3", "balancer.py"]

