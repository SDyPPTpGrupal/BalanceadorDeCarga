#!/bin/bash
set -e

APP_USER="${APP_USER:-alumno}"
DEPLOY_DIR="${DEPLOY_DIR:-/deploy}"

start_backend() {
	local directory="$1"
	local port="$2"
	local python_file
	local jar_file
	local command

	python_file=$(find "${directory}" -maxdepth 1 -type f -name '*.py' -print -quit)
	jar_file=$(find "${directory}" -maxdepth 1 -type f -name '*.jar' -print -quit)

	if [ -n "${python_file}" ]; then
		printf -v command 'cd %q && exec env PORT=%q PYTHONPATH=%q python3 %q --port %q' \
			"${directory}" "${port}" "${directory}" "${python_file}" "${port}"
	elif [ -n "${jar_file}" ]; then
		printf -v command 'cd %q && exec env PORT=%q java -jar %q %q' \
			"${directory}" "${port}" "${jar_file}" "${port}"
	else
		echo "[!] No hay .py ni .jar en ${directory}; se omite el backend ${port}"
		return 0
	fi

	su -s /bin/bash -c "${command}" "${APP_USER}" &
	echo "[*] backend arrancado en ${port}: ${python_file:-${jar_file}}"
}

# Levantar sshd en background (necesita ser root)
/usr/sbin/sshd -D &
SSHD_PID=$!

echo "[*] sshd arrancado (pid ${SSHD_PID}) en puerto ${SSH_PORT:-22}"

start_backend "${DEPLOY_DIR}/vieja" 9001
start_backend "${DEPLOY_DIR}/nueva" 9002

# Correr el balancer como el usuario alumno, en background
su -s /bin/bash -c "cd /app && exec python3 balancer.py" "${APP_USER}" &
APP_PID=$!

echo "[*] balancer.py arrancado (pid ${APP_PID}) en puerto ${PORT:-80}"

# El balanceador y SSH mantienen vivo el contenedor; un backend puede fallar sin
# apagar el otro, para que el switch pueda rechazarlo por health check.
wait -n "${SSHD_PID}" "${APP_PID}"
exit $?
