FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

ARG APP_USER=alumno
ARG APP_PASSWORD=alumno
ARG PORT=8080
ARG SSH_PORT=22

ENV PORT=${PORT}
ENV SSH_PORT=${SSH_PORT}
ENV APP_USER=${APP_USER}

# Instalar SSH, Python, Java y herramientas básicas
RUN apt-get update && \
    apt-get install -y \
        openssh-server \
        sudo \
        openjdk-21-jre-headless \
        python3 \
        python3-pip \
        curl \
        iputils-ping \
        net-tools \
        nano && \
    rm -rf /var/lib/apt/lists/*

# Crear directorio necesario para SSH
RUN mkdir -p /run/sshd

# Crear usuario para los alumnos
RUN useradd -m -s /bin/bash "${APP_USER}"

# Establecer contraseña
RUN echo "${APP_USER}:${APP_PASSWORD}" | chpasswd

# Dar sudo al usuario
RUN echo "${APP_USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/"${APP_USER}"

# Configuración SSH
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

WORKDIR /app

# Instalar dependencias del balancer, incluido grpcio-tools para generar los stubs del proto
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

# Copiar el script del balanceador y los stubs gRPC generados localmente desde contrato.proto
COPY balancer.py ./
COPY contrato_pb2.py ./
COPY contrato_pb2_grpc.py ./

# Script de arranque: levanta sshd (root) y balancer.py (como usuario alumno) juntos
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# El usuario alumno necesita poder leer/escribir en /app (para recibir archivos por SCP)
RUN chown -R "${APP_USER}:${APP_USER}" /app

# 22: SSH para que los equipos entren a deployar
# 8080 (o el PORT que definas): balanceador (única URL pública del servicio)
# 9001, 9002: puertos internos de las apps Python/Java (ajustar si usan otros)
EXPOSE ${SSH_PORT}
EXPOSE ${PORT}
EXPOSE 9001
EXPOSE 9002

ENTRYPOINT ["/entrypoint.sh"]
