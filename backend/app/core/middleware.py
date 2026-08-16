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


class TenancyMiddleware:
    def __init__(self, app: ASGIApp, auth_backend: AuthBackend) -> None:
        self.app = app
        self.auth_backend = auth_backend

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in PUBLIC_PATHS:
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
