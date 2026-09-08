#!/bin/bash
set -e

APP_USER="${APP_USER:-balancer}"

# Levantar sshd en background (necesita ser root)
/usr/sbin/sshd -D &
SSHD_PID=$!

echo "[*] sshd arrancado (pid ${SSHD_PID}) en puerto ${SSH_PORT:-22}"

# Correr el balancer como usuario no privilegiado, en foreground
su -s /bin/bash -c "cd /app && exec python3 balancer.py" "${APP_USER}" &
APP_PID=$!

# Si cualquiera de los dos procesos muere, matamos el contenedor entero
wait -n "${SSHD_PID}" "${APP_PID}"
exit $?
