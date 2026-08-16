"""Autoservicio de ajustes de módulo (Fase 17): el admin de organización edita
los ajustes de sus propios módulos (por ahora, el patrón de numeración de
presupuestos/albaranes/facturas) sin depender del superadmin.

Mismo patrón que `permisos_router.tenant_router`: gated por
`require_admin_organizacion`, resuelve `cuenta_id` a partir de
`principal.organization_id` — nunca lo acepta como parámetro de ruta, para no
poder cruzar la frontera de cuenta ajena.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.database import get_session
from app.core.numeracion import PatronInvalido
from app.modules.core import cuenta_service
from app.modules.core.cuenta_schemas import PatronNumeracionOut, PatronNumeracionUpdate
from app.modules.core.tenant_utils import cuenta_id_del_principal

tenant_router = APIRouter(
    prefix="/ajustes", tags=["ajustes"], dependencies=[Depends(require_admin_organizacion)]
)


class NumeracionInfoOut(BaseModel):
    patrones: list[PatronNumeracionOut]
    cifs_distintos: bool


@tenant_router.get("/numeracion", response_model=NumeracionInfoOut)
async def numeracion_tenant(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> NumeracionInfoOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    return NumeracionInfoOut(
        patrones=await cuenta_service.listar_patrones_numeracion(session, cuenta_id),
        cifs_distintos=await cuenta_service.cifs_distintos_de_cuenta(session, cuenta_id),
    )


@tenant_router.put("/numeracion/{tipo_documento}", response_model=PatronNumeracionOut)
async def actualizar_numeracion_tenant(
    tipo_documento: str,
    datos: PatronNumeracionUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> PatronNumeracionOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        return await cuenta_service.actualizar_patron_numeracion(session, cuenta_id, tipo_documento, datos)
    except PatronInvalido as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
