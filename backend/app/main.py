import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import build_auth_backend
from app.core.config import get_settings
from app.core.middleware import TenancyMiddleware
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
    yield


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

    return app


app = create_app()
