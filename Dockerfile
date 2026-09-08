FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

ARG APP_USER=alumno
ARG APP_PASSWORD=alumno
ARG PORT=80
ARG SSH_PORT=22

ENV PORT=${PORT}
ENV SSH_PORT=${SSH_PORT}
ENV APP_USER=${APP_USER}
ENV DEPLOY_DIR=/deploy
ENV OLD_BACKEND_URL=http://host.docker.internal:9001
ENV NEW_BACKEND_URL=http://host.docker.internal:9002

# Instalar solo lo necesario para SSH/SCP, el balanceador Python y los JAR Java
RUN apt-get update && \
    apt-get install -y \
        openssh-server \
        openjdk-21-jre-headless \
        python3 \
        python3-pip \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Crear directorios necesarios para SSH y archivos subidos por SCP
RUN mkdir -p /run/sshd /deploy/vieja /deploy/nueva

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

# Instalar dependencias necesarias en tiempo de ejecución
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

# Copiar el script del balanceador y los stubs gRPC generados localmente desde contrato.proto
COPY balancer.py ./
COPY contrato_pb2.py ./
COPY contrato_pb2_grpc.py ./

# Script de arranque: levanta sshd (root) y balancer.py (como usuario alumno) juntos
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# El usuario alumno necesita poder leer/escribir en el código y en los archivos subidos por SCP
RUN chown -R "${APP_USER}:${APP_USER}" /app /deploy

# 22: SSH para que los equipos entren a deployar
# 80 (o el PORT que definas): API HTTP pública del balanceador
EXPOSE ${SSH_PORT}
EXPOSE ${PORT}

ENTRYPOINT ["/entrypoint.sh"]
