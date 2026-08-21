import uuid
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.tenancy import current_organization_id

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Sesión por request.

    Publica la organización activa en la conexión como `app.organization_id`.
    Hoy es informativo; en Fase 5 son las políticas RLS de PostgreSQL las que
    leen esta variable, y el mecanismo ya estará en su sitio.
    """
    async with SessionFactory() as session:
        org_id = current_organization_id()
        if org_id is not None:
            await session.execute(
                text("SELECT set_config('app.organization_id', :org_id, true)"),
                {"org_id": str(org_id)},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


from app.core import auditoria  # noqa: E402,F401  registra el listener de historial de cambios


async def fijar_organizacion_activa(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Cambia qué organización ve esta sesión para el resto de la transacción.

    Uso exclusivo de los endpoints de administración (rol superadmin): son los
    únicos que legítimamente necesitan operar sobre una organización distinta
    de la del propio principal autenticado. `set_config(..., true)` es local a
    la transacción — no se filtra a otras peticiones que reutilicen la misma
    conexión del pool, igual que el `app.organization_id` que fija
    `get_session()` al principio de cada request.
    """
    await session.execute(
        text("SELECT set_config('app.organization_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
