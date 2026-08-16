"""Overrides de traducción de la interfaz (Fase 19), en dos sabores:

- `router`: lectura, cualquier usuario autenticado — el frontend los funde
  sobre el bundle base de español al arrancar (`i18n.addResourceBundle`).
- `tenant_router`: autoservicio de edición, gated por
  `require_admin_organizacion`, mismo patrón que `ajustes_router.py` /
  `diccionario_router.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.database import get_session
from app.modules.core import traduccion_service
from app.modules.core.traduccion_schemas import TraduccionOverrideOut, TraduccionOverrideUpdate
from app.modules.core.tenant_utils import cuenta_id_del_principal

router = APIRouter(prefix="/traducciones", tags=["traducciones"])
tenant_router = APIRouter(
    prefix="/ajustes/traduccion",
    tags=["ajustes"],
    dependencies=[Depends(require_admin_organizacion)],
)


@router.get("", response_model=dict[str, str])
async def obtener_overrides(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    # El personal de la plataforma (Fase 13) no pertenece a ninguna
    # organización/cuenta: no hay overrides que fundir, como `list_modules`
    # ya hace para /api/modules.
    if principal.organization_id is None:
        return {}
    cuenta_id = await cuenta_id_del_principal(session, principal)
    overrides = await traduccion_service.listar_overrides(session, cuenta_id)
    return {o.clave: o.texto for o in overrides}


@tenant_router.get("", response_model=list[TraduccionOverrideOut])
async def listar_overrides_tenant(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> list[TraduccionOverrideOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    overrides = await traduccion_service.listar_overrides(session, cuenta_id)
    return [TraduccionOverrideOut.model_validate(o) for o in overrides]


@tenant_router.put("/{clave}", response_model=TraduccionOverrideOut)
async def establecer_override_tenant(
    clave: str,
    datos: TraduccionOverrideUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> TraduccionOverrideOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    override = await traduccion_service.establecer_override(session, cuenta_id, clave, datos.texto)
    return TraduccionOverrideOut.model_validate(override)


@tenant_router.delete("/{clave}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_override_tenant(
    clave: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> None:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    if not await traduccion_service.eliminar_override(session, cuenta_id, clave):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override no encontrado")
