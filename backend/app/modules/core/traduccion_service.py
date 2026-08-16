import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core.traduccion_models import TraduccionOverride


async def listar_overrides(session: AsyncSession, cuenta_id: uuid.UUID) -> list[TraduccionOverride]:
    filas = await session.execute(
        select(TraduccionOverride)
        .where(TraduccionOverride.cuenta_id == cuenta_id)
        .order_by(TraduccionOverride.clave)
    )
    return list(filas.scalars())


async def establecer_override(
    session: AsyncSession, cuenta_id: uuid.UUID, clave: str, texto: str
) -> TraduccionOverride:
    override = await session.scalar(
        select(TraduccionOverride).where(
            TraduccionOverride.cuenta_id == cuenta_id, TraduccionOverride.clave == clave
        )
    )
    if override is None:
        override = TraduccionOverride(cuenta_id=cuenta_id, clave=clave, texto=texto)
        session.add(override)
    else:
        override.texto = texto
    await session.flush()
    return override


async def eliminar_override(session: AsyncSession, cuenta_id: uuid.UUID, clave: str) -> bool:
    override = await session.scalar(
        select(TraduccionOverride).where(
            TraduccionOverride.cuenta_id == cuenta_id, TraduccionOverride.clave == clave
        )
    )
    if override is None:
        return False
    await session.delete(override)
    await session.flush()
    return True
