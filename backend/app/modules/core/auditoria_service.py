import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core.auditoria_models import RegistroAuditoria


async def listar_historial(
    session: AsyncSession, *, tabla: str, registro_id: uuid.UUID
) -> list[RegistroAuditoria]:
    """RLS ya limita esto a la organización activa; `tabla`+`registro_id`
    acotan al registro concreto. El llamador es responsable de comprobar
    antes que el usuario puede VER ese registro (mismo permiso que su ficha,
    incluido "solo lo mío") — esta función no repite esa comprobación."""
    filas = await session.execute(
        select(RegistroAuditoria)
        .where(RegistroAuditoria.tabla == tabla, RegistroAuditoria.registro_id == registro_id)
        .order_by(RegistroAuditoria.created_at.desc())
    )
    return list(filas.scalars())
