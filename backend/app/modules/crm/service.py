import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.crm.models import EntidadNota, Nota
from app.modules.crm.schemas import NotaCreate


async def listar_notas(session: AsyncSession, entidad: EntidadNota, entidad_id: uuid.UUID) -> list[Nota]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(Nota)
        .where(
            Nota.organization_id == org_id,
            Nota.entidad == entidad,
            Nota.entidad_id == entidad_id,
        )
        .order_by(Nota.created_at.desc())
    )
    return list(filas.scalars())


async def crear_nota(
    session: AsyncSession, entidad: EntidadNota, entidad_id: uuid.UUID, datos: NotaCreate
) -> Nota:
    org_id = require_organization_id()
    nota = Nota(
        organization_id=org_id,
        entidad=entidad,
        entidad_id=entidad_id,
        contenido=datos.contenido,
        **datos_autoria(),
    )
    session.add(nota)
    await session.flush()
    return nota


async def eliminar_nota(session: AsyncSession, nota_id: uuid.UUID) -> bool:
    org_id = require_organization_id()
    nota = await session.scalar(
        select(Nota).where(Nota.id == nota_id, Nota.organization_id == org_id)
    )
    if nota is None:
        return False
    await session.delete(nota)
    await session.flush()
    return True
