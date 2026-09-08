FROM alpine:latest

# Evitar buffering en la salida estándar de Python para ver logs en tiempo real
ENV PYTHONUNBUFFERED=1

# Argumentos configurables para no quemar usuarios ni puertos en el código del Dockerfile
ARG APP_USER=balancer
ARG APP_GROUP=balancer
ARG PORT=80
ARG SSH_PORT=22
ARG APP_PASSWORD=changeme

# Variables de entorno de ejecución
ENV PORT=${PORT}
ENV SSH_PORT=${SSH_PORT}

# Instalar Python 3, pip, libcap (para bindear puertos bajos sin ser root), curl y openssh
RUN apk add --no-cache \
        python3 \
        py3-pip \
        openjdk17-jre \
        libcap \
        curl \
        openssh \
        bash && \
    setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))

# Crear usuario y grupo no privilegiados configurables
RUN addgroup -S "${APP_GROUP}" && adduser -S -G "${APP_GROUP}" -h /app -s /bin/bash "${APP_USER}"

# Configurar SSH: generar host keys, permitir login por password para el usuario app,
# y setear la contraseña (cambiala en runtime idealmente con -e o mejor: usar claves públicas)
RUN ssh-keygen -A && \
    echo "${APP_USER}:${APP_PASSWORD}" | chpasswd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i "s/#Port 22/Port ${SSH_PORT}/" /etc/ssh/sshd_config && \
    echo "AllowUsers ${APP_USER}" >> /etc/ssh/sshd_config

WORKDIR /app

# Instalar dependencias, incluido grpcio-tools para generar los stubs del proto
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

# Copiar el script del balanceador
COPY balancer.py ./

# Copiar los stubs gRPC generados localmente desde contrato.proto
COPY contrato_pb2.py ./
COPY contrato_pb2_grpc.py ./

# Script de arranque: levanta sshd (como root, en background) y el balancer (como usuario app)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Asignar permisos al usuario de la aplicación
RUN chown -R "${APP_USER}:${APP_GROUP}" /app

# Puertos internos parametrizados
EXPOSE ${PORT} ${SSH_PORT}

# NOTA: no usamos USER acá porque sshd necesita arrancar como root.
# El entrypoint.sh es quien baja privilegios para correr balancer.py como ${APP_USER}.
ENTRYPOINT ["/entrypoint.sh"]
