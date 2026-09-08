# Balanceador - Etapa 1

Balanceador HTTP con dos backends internos gRPC. En esta etapa no hay round-robin: siempre se atiende con un unico backend activo. El cambio de version se hace sin reiniciar el balanceador y permite rollback.

```text
Cliente HTTP
    |
    | Windows:Tailscale:89
    v
Balanceador HTTP (contenedor:80)
    |
    +--> backend viejo gRPC: 127.0.0.1:9001
    |
    +--> backend nuevo gRPC: 127.0.0.1:9002
```

## Requisitos

- Docker Desktop funcionando en Windows.
- Tailscale conectado en el Windows anfitrion.
- La imagen instala Python 3 y Java 21 para ejecutar los archivos subidos dentro del contenedor.
- Cada backend debe implementar el servicio definido en `contrato.proto` y escuchar por gRPC.

## Puertos

| Puerto Windows | Contenedor | Uso |
|---:|---:|---|
| `89` | `80` | API HTTP publica del balanceador |
| `2222` | `22` | SSH/SCP para subir archivos |
| `9001` | interno | Backend viejo, gRPC dentro del contenedor |
| `9002` | interno | Backend nuevo, gRPC dentro del contenedor |
| `8088` | interno | Control local del balanceador |

Desde otra casa solo deben ser accesibles por Tailscale los puertos `89` y `2222`. No hace falta publicar `9001`, `9002` ni `8088`.

## Configuracion inicial

Desde PowerShell, ubicado en este directorio:

```powershell
Copy-Item .env.example .env
```

Editar `.env` y cambiar como minimo:

```env
APP_USER=balancer
APP_PASSWORD=una-clave
PUBLIC_PORT=89
SCP_PORT=2222
OLD_BACKEND_URL=http://host.docker.internal:9001
NEW_BACKEND_URL=http://host.docker.internal:9002
```

Los backends se ejecutan dentro del mismo contenedor y el balanceador los alcanza por `127.0.0.1`. No es necesario instalar Python ni Java en Windows.

## Levantar el balanceador

```powershell
docker compose up -d --build
```

Ver el estado del contenedor:

```powershell
docker compose ps
docker compose logs -f balanceador
```

Probar desde el Windows:

```powershell
curl.exe http://localhost:89/health
curl.exe http://localhost:89/
curl.exe -X POST http://localhost:89/echo -H "Content-Type: application/json" -d '{"ping":"hola"}'
```

Desde otra casa, reemplazar `IP_TAILSCALE_WINDOWS` por la IP Tailscale del Windows:

```powershell
curl.exe http://IP_TAILSCALE_WINDOWS:89/health
```

## Subir archivos por SCP

La cuenta SSH es el valor de `APP_USER`. La clave es la definida por `APP_PASSWORD` al construir la imagen.

Subir la version vieja:

```powershell
scp -P 2222 app-vieja.py usuario@IP_TAILSCALE_WINDOWS:/deploy/vieja/
scp -P 2222 app-viejo.jar usuario@IP_TAILSCALE_WINDOWS:/deploy/vieja/
```

Subir la version nueva:

```powershell
scp -P 2222 app-nueva.py usuario@IP_TAILSCALE_WINDOWS:/deploy/nueva/
scp -P 2222 app-nuevo.jar usuario@IP_TAILSCALE_WINDOWS:/deploy/nueva/
```

Los archivos quedan en las carpetas `deploy/vieja` y `deploy/nueva` del workspace de Windows, montadas dentro del contenedor como `/deploy`.

Subir un archivo no lo ejecuta automaticamente. Hay que iniciar cada backend dentro del contenedor como proceso gRPC separado.

## Iniciar los backends

Los comandos exactos dependen de los archivos entregados por los equipos. La idea es:

```powershell
docker compose exec -d balanceador sh -c "PORT=9001 python3 /deploy/vieja/app.py"
```

Para iniciar la version nueva en Java:

```powershell
docker compose exec -d balanceador java -jar /deploy/nueva/app.jar --port=9002
```

Si la version vieja es Java:

```powershell
docker compose exec -d balanceador java -jar /deploy/vieja/app.jar --port=9001
```

Si la version nueva es Python:

```powershell
docker compose exec -d balanceador sh -c "PORT=9002 python3 /deploy/nueva/app.py"
```

Los nombres `app.py`, `app.jar` y la opcion `--port` son ejemplos: reemplazarlos por los nombres y argumentos reales de cada equipo. Si un Python subido tiene dependencias adicionales, subir tambien su `requirements.txt` e instalarlas dentro del contenedor:

```powershell
docker compose exec balanceador pip3 install -r /deploy/nueva/requirements.txt --break-system-packages
```

Antes de conmutar, verificar que el backend nuevo responda al RPC `Salud` y devuelva `SANO`.

## Conmutar y hacer rollback

El control escucha solamente dentro del contenedor, en `127.0.0.1:8088`. Se puede invocar desde el Windows con `docker compose exec`.

Conmutar a la version nueva:

```powershell
docker compose exec balanceador curl.exe -s -X POST http://127.0.0.1:8088/__switch -H "Content-Type: application/json" -d '{"version":"nueva"}'
```

Volver a la version vieja:

```powershell
docker compose exec balanceador curl.exe -s -X POST http://127.0.0.1:8088/__switch -H "Content-Type: application/json" -d '{"version":"vieja"}'
```

Rollback al backend anterior:

```powershell
docker compose exec balanceador curl.exe -s -X POST http://127.0.0.1:8088/__rollback
```

Consultar el backend activo:

```powershell
docker compose exec balanceador curl.exe -s http://127.0.0.1:8088/__status
```

`__switch` primero consulta `Salud`. Si la version nueva no esta sana, la conmutacion devuelve `503` y el backend anterior sigue atendiendo.

## Apagar y limpiar

```powershell
docker compose down
```

Para borrar tambien la imagen construida:

```powershell
docker compose down --rmi local
```

## Firewall de Windows

Tailscale no requiere abrir puertos en el router. El Firewall de Windows debe permitir TCP entrante en `89` y `2222` para la interfaz/red de Tailscale. Los puertos internos `9001`, `9002` y `8088` no se publican.
