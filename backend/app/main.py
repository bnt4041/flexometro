import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import build_auth_backend
from app.core.config import get_settings
from app.core.middleware import (
    PUBLIC_PREFIXES,
    RUTAS_PUBLICAS_PERMITIDAS,
    TenancyMiddleware,
)
from app.core.modules import registry
from app.core.storage import asegurar_bucket
from app.modules import register_all

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("obras")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Módulos registrados: %s", ", ".join(sorted(spec.code for spec in registry.all()))
    )
    try:
        await asegurar_bucket()
    except Exception:
        logger.warning("No se pudo preparar el bucket de MinIO; el gestor documental fallará", exc_info=True)
    try:
        from app.modules.presupuestos.plantilla_docx_service import asegurar_plantillas_sistema

        await asegurar_plantillas_sistema()
    except Exception:
        logger.warning("No se pudieron preparar las plantillas de sistema", exc_info=True)

    # Catálogo de avisos y su latido. La tarea se guarda para poder pararla
    # al apagar: sin eso, un reinicio en caliente dejaría dos evaluando.
    from app.modules.notificaciones import vigilancia
    from app.modules.notificaciones.eventos import registrar_catalogo_inicial

    registrar_catalogo_inicial()

    from app.modules.automatizaciones import nodos as nodos_automatizacion
    from app.modules.automatizaciones import service as automatizaciones
    from app.modules.desarrolladores import webhooks

    nodos_automatizacion.registrar_catalogo_inicial()

    from app.modules.importador.destinos import registrar_catalogo_inicial as _destinos

    _destinos()

    from app.modules.informes.fuentes import registrar_catalogo_inicial as _fuentes

    _fuentes()

    tareas = [
        asyncio.create_task(vigilancia.bucle()),
        asyncio.create_task(webhooks.bucle()),
        asyncio.create_task(automatizaciones.bucle()),
    ]

    try:
        yield
    finally:
        for tarea in tareas:
            tarea.cancel()
        for tarea in tareas:
            with suppress(asyncio.CancelledError):
                await tarea


def _verificar_rutas_publicas(app: FastAPI) -> None:
    """Falla el arranque si alguien cuelga una ruta nueva del espacio sin
    autenticar sin declararla como tal.

    `PUBLIC_PREFIXES` deja fuera del middleware de tenancy todo lo que empiece
    por ese prefijo — es decir, sin sesión, sin organización en contexto y sin
    `require_permiso`. Eso es correcto para la separata del proveedor, que se
    autoriza contra el token de su enlace, pero es una trampa para el
    siguiente que monte un router ahí sin darse cuenta. Que reviente al
    arrancar es mucho mejor que descubrirlo en producción.
    """
    montadas = {
        ruta.path
        for ruta in app.routes
        if getattr(ruta, "path", "").startswith(PUBLIC_PREFIXES)
    }
    no_declaradas = montadas - RUTAS_PUBLICAS_PERMITIDAS
    if no_declaradas:
        raise RuntimeError(
            "Hay rutas bajo el espacio público sin declarar en "
            f"RUTAS_PUBLICAS_PERMITIDAS: {sorted(no_declaradas)}. "
            "Cualquier ruta ahí queda SIN autenticar: decláralas a conciencia "
            "en app/core/middleware.py o móntalas fuera de ese prefijo."
        )


def create_app() -> FastAPI:
    # El registro se puebla antes de montar routers; validate_dependencies()
    # revienta aquí y no en la primera request si el grafo es inválido.
    register_all()

    app = FastAPI(
        title="ERP de construcción — API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenancyMiddleware, auth_backend=build_auth_backend(settings))

    for spec in registry.all():
        if spec.router is not None:
            app.include_router(spec.router)

    @app.get("/health", tags=["infra"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    @app.get("/api/config", tags=["infra"])
    async def config() -> dict[str, str | None]:
        """Configuración pública que el frontend necesita para iniciar sesión.

        Se sirve en tiempo de ejecución en vez de compilarla en el bundle: así
        el mismo build vale para desarrollo y para producción, y cambiar el
        realm no obliga a reconstruir el frontend.
        """
        if settings.auth_backend != "keycloak":
            return {"auth": settings.auth_backend, "url": None, "realm": None, "client_id": None}
        return {
            "auth": "keycloak",
            "url": settings.keycloak_public_url,
            "realm": settings.keycloak_realm,
            "client_id": "obras-web",
        }

    _verificar_rutas_publicas(app)
    return app


app = create_app()
