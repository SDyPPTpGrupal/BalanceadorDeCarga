# TpGrupalEquipoPlataforma

Parte 1 del TP Grupal — Sistemas Distribuidos y Programación Paralela.

## Integrantes

- Mateo
- Juan

## Qué hicimos

Montamos un servidor compartido (un container Docker) donde los otros dos
equipos (Java y Python) pueden entrar por SSH y desplegar sus apps. El
container expone dos puertos hacia afuera con ngrok: uno para SSH y otro
para el tráfico HTTP del servicio.

## Diagrama de arquitectura

![Arquitectura Parte 1](diagrama-arquitectura-parte1.png)

El servidor es un recurso compartido operado por el equipo de Plataforma
(el "cloud provider"): ellos lo montan y reparten el acceso, pero no lo
usan para su propia app. Dentro corre un container Docker (Ubuntu 24.04)
con dos procesos escuchando en los puertos internos **22** (SSH) y **80**
(HTTP). Docker mapea esos puertos internos a puertos distintos en la
máquina host, y un túnel los expone a internet con una URL pública.

Dos casas remotas (los equipos de Java y Python) se conectan a esos
puertos — y ahí está el punto central de la Parte 1: **compiten por el
mismo puerto de producción**. Solo una app puede tenerlo ocupado a la
vez; desplegar significa parar a la que está y levantar la propia.

## Mapeo de puertos

| Servicio | Puerto interno (container) | Puerto externo (host) |
|----------|:---:|:---:|
| SSH      | 22  | 2222 |
| HTTP     | 80  | 8080 |

Esto es clave: **el container nunca escucha directamente en 2222 ni en
8080** — esos son los puertos del host que Docker redirige hacia adentro.
Dentro del container siempre se habla de 22 y 80, los puertos estándar.

## Cómo levantarlo

```bash
docker build -t plataforma-clase2 .

docker run -d \
  --name servidor \
  -p 2222:22 \
  -p 8080:80 \
  -v $(pwd)/logs:/home/alumno/logs \
  plataforma-clase2
```

El flag `-p host:container` es el que hace el mapeo: `-p 2222:22` conecta
el puerto 2222 del host al puerto 22 dentro del container, y
`-p 8080:80` hace lo mismo para HTTP.

## Cómo exponerlo con ngrok

```bash
ngrok tcp 2222     # para que los otros equipos entren por SSH
ngrok http 8080    # la URL pública del servicio HTTP
```

Nota: correr dos túneles ngrok a la vez puede requerir plan pago según la
cuenta — confirmar disponibilidad antes de la demo.

## Acceso SSH

Usuario: `alumno`
Contraseña: `alumno`
Puerto: el que indique ngrok para el túnel TCP (o `2222` si están en la
misma red que el servidor).
