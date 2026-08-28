"""Middleware de tenancy.

Es ASGI puro a propósito, no `BaseHTTPMiddleware`: este último ejecuta el resto
de la aplicación en otra tarea, y un ContextVar fijado antes de `call_next` no
llega de forma fiable al endpoint. En ASGI puro la llamada ocurre en la misma
tarea y el contexto propaga.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.auth import AuthBackend, SinAutenticar, SinOrganizacion
from app.core.database import SessionFactory
from app.core.tenancy import (
    reset_organization_id,
    reset_principal,
    set_organization_id,
    set_principal,
)

# Rutas que no necesitan organización activa.
PUBLIC_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json", "/api/config"})

# Espacio sin autenticar, por prefijo en vez de por ruta exacta: lo usa la
# separata que rellena un proveedor externo, que llega desde un enlace de
# correo y no tiene cuenta en el sistema. Cada endpoint de aquí dentro se
# autoriza a sí mismo contra el token de la URL y fija a mano el contexto de
# organización (ver `compras/publico_router.py`).
#
# ⚠️ Montar un router bajo este prefijo lo deja SIN autenticar y SIN
# `require_permiso`, en silencio. Para que eso no pase por descuido,
# `app.main.create_app` comprueba al arrancar que las rutas que cuelgan de
# aquí son exactamente las de la lista blanca `RUTAS_PUBLICAS_PERMITIDAS`.
PUBLIC_PREFIXES = ("/api/publico/",)

# Lista blanca de lo que legítimamente vive bajo `PUBLIC_PREFIXES`, con el
# formato de `APIRoute.path`. Añadir algo aquí es una decisión de seguridad
# consciente, no un efecto colateral de crear un router.
RUTAS_PUBLICAS_PERMITIDAS = frozenset(
    {
        "/api/publico/oferta/{token}",
        "/api/publico/oferta/{token}/lineas",
        "/api/publico/oferta/{token}/enviar",
        # Documentos que el EMISOR adjuntó al borrador antes de enviarlo: de
        # solo lectura para el proveedor. Subir es cosa aparte, y solo por la
        # ruta de IA de más abajo, que no guarda el fichero.
        "/api/publico/oferta/{token}/documentos",
        "/api/publico/oferta/{token}/documentos/{documento_id}/descargar",
        # El estado de mediciones que aporta el proveedor. Vive en su propia
        # tabla (`compras.oferta_medicion`), no en la del presupuesto del
        # emisor: es SU medición y no debe tocar el presupuesto de cliente.
        "/api/publico/oferta/{token}/lineas/{linea_id}/mediciones",
        "/api/publico/oferta/{token}/mediciones/{medicion_id}",
        # Cómo desglosa el proveedor su precio. También en tabla propia
        # (`compras.oferta_descompuesto`) y sin referencia al banco de
        # precios: el banco es del emisor.
        "/api/publico/oferta/{token}/lineas/{linea_id}/descompuesto",
        "/api/publico/oferta/{token}/descompuesto/{componente_id}",
        # Lectura con IA del documento de precios del proveedor. La paga el
        # EMISOR (el contexto público está fijado a su organización), y por eso
        # lleva tope de usos por enlace: ver MAX_USOS_IA en publico_router.
        "/api/publico/oferta/{token}/ia/documento",
        # Prueba de concepto del medidor por foto (ver testmeter/router.py):
        # sin token porque no está atada a ninguna obra ni organización, solo
        # a la clave de Gemini del .env — limitada por IP en vez de por enlace.
        "/api/publico/testmeter/escala",
    }
)


def es_ruta_publica(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


class TenancyMiddleware:
    def __init__(self, app: ASGIApp, auth_backend: AuthBackend) -> None:
        self.app = app
        self.auth_backend = auth_backend

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or es_ruta_publica(scope["path"]):
            await self.app(scope, receive, send)
            return

        # El preflight de CORS viaja sin cabecera Authorization por definición;
        # rechazarlo con 401 rompería todas las llamadas del navegador.
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        try:
            async with SessionFactory() as session:
                principal = await self.auth_backend.authenticate(request, session)
        except SinAutenticar as exc:
            await _responder(scope, receive, send, 401, str(exc), autenticar=True)
            return
        except SinOrganizacion as exc:
            await _responder(scope, receive, send, 403, str(exc))
            return
        except LookupError as exc:
            await _responder(scope, receive, send, 401, str(exc))
            return

        scope.setdefault("state", {})["principal"] = principal
        token_org = set_organization_id(principal.organization_id)
        token_principal = set_principal(principal)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_principal(token_principal)
            reset_organization_id(token_org)


async def _responder(
    scope: Scope,
    receive: Receive,
    send: Send,
    codigo: int,
    detalle: str,
    *,
    autenticar: bool = False,
) -> None:
    cabeceras = {"WWW-Authenticate": "Bearer"} if autenticar else None
    await JSONResponse({"detail": detalle}, status_code=codigo, headers=cabeceras)(
        scope, receive, send
    )
