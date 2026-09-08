#!/bin/bash
set -e

APP_USER="${APP_USER:-alumno}"

# Levantar sshd en background (necesita ser root)
/usr/sbin/sshd -D &
SSHD_PID=$!

echo "[*] sshd arrancado (pid ${SSHD_PID}) en puerto ${SSH_PORT:-22}"

# Correr el balancer como el usuario alumno, en background
su -s /bin/bash -c "cd /app && exec python3 balancer.py" "${APP_USER}" &
APP_PID=$!

echo "[*] balancer.py arrancado (pid ${APP_PID}) en puerto ${PORT:-8080}"

# Si cualquiera de los dos procesos muere, el contenedor entero se cae
wait -n "${SSHD_PID}" "${APP_PID}"
exit $?
