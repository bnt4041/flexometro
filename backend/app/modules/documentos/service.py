import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.documentos.models import Documento, EntidadDocumento


async def listar_documentos(
    session: AsyncSession, entidad: EntidadDocumento, entidad_id: uuid.UUID
) -> list[Documento]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(Documento)
        .where(
            Documento.organization_id == org_id,
            Documento.entidad == entidad,
            Documento.entidad_id == entidad_id,
        )
        .order_by(Documento.created_at.desc())
    )
    return list(filas.scalars())


async def obtener_documento(session: AsyncSession, documento_id: uuid.UUID) -> Documento | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Documento).where(Documento.id == documento_id, Documento.organization_id == org_id)
    )


async def subir_documento(
    session: AsyncSession,
    entidad: EntidadDocumento,
    entidad_id: uuid.UUID,
    nombre_archivo: str,
    content_type: str,
    contenido: bytes,
) -> Documento:
    org_id = require_organization_id()
    object_key = f"{org_id}/{entidad}/{entidad_id}/{uuid.uuid4()}-{nombre_archivo}"
    await storage.subir_objeto(object_key, contenido, content_type)

    documento = Documento(
        organization_id=org_id,
        entidad=entidad,
        entidad_id=entidad_id,
        nombre_archivo=nombre_archivo,
        content_type=content_type,
        tamano_bytes=len(contenido),
        object_key=object_key,
        **datos_autoria(),
    )
    session.add(documento)
    await session.flush()
    return documento


async def eliminar_documento(session: AsyncSession, documento_id: uuid.UUID) -> bool:
    documento = await obtener_documento(session, documento_id)
    if documento is None:
        return False
    await storage.eliminar_objeto(documento.object_key)
    await session.delete(documento)
    await session.flush()
    return True
