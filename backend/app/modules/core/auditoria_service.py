import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core.auditoria_models import AccionAuditoria, RegistroAuditoria


async def registrar_evento(
    session: AsyncSession,
    *,
    tabla: str,
    registro_id: uuid.UUID,
    organization_id: uuid.UUID,
    descripcion: str,
    usuario_subject: str | None,
    usuario_nombre: str | None,
) -> RegistroAuditoria:
    """Para acciones del servidor que no son un diff de columnas de la propia
    entidad (ver `AccionAuditoria.EVENTO`) — la IA añadiendo un capítulo con
    partidas a un presupuesto, por ejemplo. El listener de
    `app.core.auditoria` cubre creado/modificado/eliminado solo; esto es lo
    que llama explícitamente el servicio que dispara la acción."""
    fila = RegistroAuditoria(
        organization_id=organization_id,
        tabla=tabla,
        registro_id=registro_id,
        accion=AccionAuditoria.EVENTO,
        cambios=None,
        descripcion=descripcion,
        usuario_subject=usuario_subject,
        usuario_nombre=usuario_nombre,
    )
    session.add(fila)
    await session.flush()
    return fila


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
