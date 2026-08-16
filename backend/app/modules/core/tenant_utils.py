"""Helper compartido por los routers de autoservicio (`tenant_router`) que
operan a nivel de cuenta: resuelve `cuenta_id` a partir de la organización
del propio principal — nunca lo acepta como parámetro de ruta, para no poder
cruzar la frontera hacia la cuenta de otro."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.modules.core import service as core_service


async def cuenta_id_del_principal(session: AsyncSession, principal: Principal) -> uuid.UUID:
    organizacion = await core_service.obtener_organizacion(session, principal.organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    return organizacion.cuenta_id
