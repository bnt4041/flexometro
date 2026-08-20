# Desplegar Flexómetro en un servidor

Todo el stack corre en contenedores Docker orquestados con Docker Compose:
Postgres, Keycloak, MinIO, la API (FastAPI) y el frontend (React/Vite),
detrás de Traefik como proxy inverso. No hace falta instalar Python ni
Node en el servidor — solo Docker.

**Antes de seguir**, lee la sección [Importante antes de ir en serio a
producción](#importante-antes-de-ir-en-serio-a-producción): el stack tal
como está en el repo ahora mismo tiene un par de cosas pensadas para
desarrollo local que conviene resolver si va a haber usuarios reales.

## 1. Requisitos del servidor

- Docker Engine 24+ y Docker Compose v2 (`docker compose`, no `docker-compose`).
- 2 vCPU / 4 GB de RAM como mínimo (Keycloak y Postgres son los que más piden).
- Un dominio (o subdominio) apuntando a la IP del servidor. Vale con uno solo
  si la API se sirve bajo `/api` del mismo dominio (así está montado en
  Traefik: ver más abajo).
- Puertos 80 (y 443 si se añade TLS, ver más abajo) abiertos.

## 2. Clonar y configurar

```bash
git clone https://github.com/bnt4041/flexometro.git
cd flexometro
cp .env.example .env
```

Edita `.env`. Como mínimo, cambia estas claves de desarrollo — el fichero
las trae con valores de ejemplo, no válidos para un servidor real:

| Variable | Por qué cambiarla |
|---|---|
| `POSTGRES_PASSWORD` | Contraseña del rol admin de Postgres |
| `APP_DB_PASSWORD` | Contraseña del rol con el que corre la API a diario |
| `KEYCLOAK_ADMIN_PASSWORD` | Contraseña del admin de Keycloak (`KEYCLOAK_ADMIN` es el usuario) |
| `MINIO_ROOT_PASSWORD` | Ya viene marcada como `change-me` en el ejemplo |
| `KEYCLOAK_PUBLIC_URL` | URL pública real por la que el navegador llega a Keycloak, p. ej. `https://obras.tudominio.com/auth` si lo cuelgas del mismo dominio, o un subdominio propio |
| `TRAEFIK_DOMAIN` | El dominio real, p. ej. `obras.tudominio.com` |
| `CORS_ORIGINS` | El origen público real de la web, p. ej. `https://obras.tudominio.com` (sin barra final) — si no coincide exactamente con lo que el navegador manda, la API rechaza las peticiones |
| `DEEPSEEK_API_KEY`, `GEMINI_API_KEY` | Opcionales: sin ellas, esas funciones de IA responden 503 en vez de fallar a medias |

`APP_ENV` puedes dejarlo en `production` una vez despliegues de verdad —
hoy solo afecta a lo que devuelve `/health`, no cambia comportamiento.

## 3. Ajustar el realm de Keycloak al dominio real

El fichero `keycloak/realm-obras.json` se importa automáticamente la
**primera vez** que arranca Keycloak (si el realm `obras` no existe todavía;
en arranques siguientes no lo vuelve a tocar). Antes de ese primer arranque,
edita los `redirectUris`/`webOrigins` del cliente `obras-web` para que
apunten al dominio real en vez de a `localhost`/`obras.localhost`:

```json
"redirectUris": ["https://obras.tudominio.com/*"],
"webOrigins": ["https://obras.tudominio.com"],
"attributes": {
  "post.logout.redirect.uris": "https://obras.tudominio.com/*"
}
```

Y **quita o cambia la contraseña del usuario de demostración** (`dev`/`dev`,
con rol `superadmin`) antes de exponer esto a internet — está pensado solo
para desarrollo local. Lo más simple es borrar el bloque `"users"` entero
del JSON antes del primer arranque y crear los usuarios reales luego desde
la consola de administración de Keycloak.

## 4. Primer arranque

```bash
docker compose --profile proxy up -d --build
```

El perfil `proxy` añade Traefik (sin él, tendrías que publicar los puertos
de `api`/`web` a mano). El orden de arranque ya está resuelto por
`depends_on` en `docker-compose.yml`: Postgres y Keycloak arrancan primero,
luego la migración (`alembic upgrade heads`, que además crea el rol de bajo
privilegio con el que corre la API) y solo cuando esa migración termina bien
arranca la API.

Comprueba que todo subió sano:

```bash
docker compose ps
docker compose logs -f migrate   # debe salir con código 0
curl -fsS http://localhost/api/health
```

`/api/health` debe devolver `{"status": "ok", "env": "production"}` (o el
valor que hayas puesto en `APP_ENV`).

## 5. TLS / HTTPS

El Traefik que trae este repo (`docker-compose.yml`, servicio `traefik`,
perfil `proxy`) solo define un entrypoint HTTP (puerto 80) — no tiene
configurado ningún resolutor ACME/Let's Encrypt. Para servir por HTTPS,
dos caminos:

- **Añadir TLS a este mismo Traefik**: un entrypoint `:443` + un
  `certificatesResolvers` de Let's Encrypt (challenge HTTP o DNS) y las
  labels de `api`/`web` actualizadas con `tls.certresolver=...`. Puedo
  añadirlo si me lo pides — no toqué esto porque implica decisiones tuyas
  (qué proveedor DNS si usas challenge DNS, qué email de contacto para
  Let's Encrypt, si quieres redirección automática de 80 a 443).
- **Poner delante un proxy que ya tengas** (Cloudflare Tunnel, otro
  Traefik/Nginx/Caddy de la máquina, un balanceador del proveedor cloud) que
  termine TLS y reenvíe en HTTP al puerto 80 de este stack. En ese caso no
  hace falta tocar nada aquí.

Sea cual sea el camino, `KEYCLOAK_PUBLIC_URL` y `CORS_ORIGINS` deben llevar
`https://`, no `http://`, para que las cookies/redirecciones de Keycloak y
las cabeceras CORS cuadren con lo que el navegador ve de verdad.

## Importante antes de ir en serio a producción

Estas tres cosas están así porque son cómodas para desarrollo local, no
porque sean lo correcto con usuarios reales. Con poco tráfico y mientras
pruebas el despliegue no van a dar problemas — pero antes de depender de
esto de verdad, conviene resolverlas:

1. **Keycloak arranca en modo `start-dev`, con su base de datos en memoria
   (H2)** (`docker-compose.yml`, servicio `keycloak`, con un comentario en
   el propio fichero avisando de esto). Eso significa que si el contenedor
   de Keycloak se reinicia o se recrea, **se pierden todos los usuarios,
   sesiones y cualquier cambio hecho desde la consola de administración**
   — solo se recupera lo que trae `realm-obras.json`. Para producción de
   verdad, Keycloak debería arrancar con `start` (no `start-dev`) y guardar
   su estado en Postgres (`KC_DB=postgres` contra la misma base de datos u
   otra), no en memoria. Dímelo si quieres que lo prepare.
2. **El frontend se sirve con el servidor de desarrollo de Vite**
   (`frontend/Dockerfile` hace `npm run dev`, no una build de producción).
   Funciona, pero es más lento y pesado de lo necesario — para producción
   normalmente se compila con `vite build` y se sirve el resultado estático
   con algo ligero (nginx, por ejemplo). También puedo prepararlo si quieres.
3. El usuario de demostración `dev`/`dev` con rol `superadmin` en
   `keycloak/realm-obras.json` — ya cubierto en el paso 3 de arriba, pero
   repetido aquí porque es el más importante: si no lo quitas antes del
   primer arranque, cualquiera que lo adivine entra como superadmin.

## 6. Actualizar tras un cambio

```bash
git pull
docker compose --profile proxy up -d --build
docker compose logs -f migrate   # por si hay migraciones nuevas
```

`--build` reconstruye solo lo que haya cambiado; si no ha cambiado nada en
`backend/`/`frontend/`, Docker reutiliza la capa cacheada.

## 7. Copias de seguridad

Los datos que importan viven en dos volúmenes nombrados de Docker:

- `pgdata` — toda la base de datos (presupuestos, terceros, todo).
- `miniodata` — los ficheros subidos al gestor documental (PDFs, imágenes,
  las imágenes incrustadas en las descripciones con formato).

```bash
docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
docker run --rm -v obras_miniodata:/data -v "$PWD":/backup alpine \
  tar czf /backup/miniodata-$(date +%F).tar.gz -C /data .
```

(El nombre real del volumen puede llevar el prefijo del proyecto — compruébalo
con `docker volume ls`.)

## Variables de entorno — resumen completo

Todas están documentadas con comentarios en `.env.example`; esta es solo la
lista para referencia rápida.

| Bloque | Variables |
|---|---|
| Postgres | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `APP_DB_USER`, `APP_DB_PASSWORD` |
| API | `API_PORT`, `APP_ENV`, `LOG_LEVEL`, `CORS_ORIGINS` |
| Autenticación | `AUTH_BACKEND`, `STUB_ORGANIZATION_SLUG`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_PUBLIC_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_WEB_CLIENT_ID`, `KEYCLOAK_PORT`, `KEYCLOAK_ADMIN`, `KEYCLOAK_ADMIN_PASSWORD` |
| IA | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL` |
| Documentos (MinIO) | `MINIO_PORT`, `MINIO_CONSOLE_PORT`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `MINIO_BUCKET` |
| Frontend | `WEB_PORT` |
| Traefik | `TRAEFIK_DOMAIN` |

`AUTH_BACKEND=stub` existe solo para pruebas/scripts locales — nunca en un
servidor con usuarios reales, porque salta la autenticación por completo.
