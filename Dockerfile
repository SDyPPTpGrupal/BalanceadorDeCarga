FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

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
RUN useradd -m -s /bin/bash alumno

# Establecer contraseña
RUN echo "alumno:alumno" | chpasswd

# Dar sudo al usuario
RUN echo "alumno ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/alumno

# Configuración SSH
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# 22: SSH para que los equipos entren a deployar
# 8080: balanceador (única URL pública del servicio)
# 9001, 9002: puertos internos de las apps Python/Java (ajustar si usan otros)
EXPOSE 22
EXPOSE 8080
EXPOSE 9001
EXPOSE 9002

CMD ["/usr/sbin/sshd", "-D"]
