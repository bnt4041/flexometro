"""Campos libres (Fase 21), en dos grupos:

- `definiciones_router` (`/api/ajustes/campos-libres/...`): autoservicio de
  definición, gated por `require_admin_organizacion`, mismo patrón que
  `diccionario_router.py` — opera sobre la cuenta del propio principal.
- `valores_router` (`/api/campos-libres/...`): lectura de qué campos existen
  (cualquier usuario, para poder pintar el formulario) y lectura/escritura de
  los valores de un registro concreto, protegida por RLS de organización
  como cualquier tabla de negocio.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.database import get_session
from app.modules.campos_libres import service
from app.modules.campos_libres.models import EntidadCampoLibre
from app.modules.campos_libres.schemas import (
    CampoLibreDefinicionCreate,
    CampoLibreDefinicionOut,
    CampoLibreDefinicionUpdate,
    ValoresCampoLibreUpdate,
)
from app.modules.core.tenant_utils import cuenta_id_del_principal

router = APIRouter()

definiciones_router = APIRouter(
    prefix="/api/ajustes/campos-libres",
    tags=["ajustes"],
    dependencies=[Depends(require_admin_organizacion)],
)
valores_router = APIRouter(prefix="/api/campos-libres", tags=["campos-libres"])


@definiciones_router.get("/{entidad}", response_model=list[CampoLibreDefinicionOut])
async def listar_definiciones_tenant(
    entidad: EntidadCampoLibre,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[CampoLibreDefinicionOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    definiciones = await service.listar_definiciones(session, cuenta_id, entidad)
    return [CampoLibreDefinicionOut.model_validate(d) for d in definiciones]


@definiciones_router.post("/{entidad}", response_model=CampoLibreDefinicionOut, status_code=status.HTTP_201_CREATED)
async def crear_definicion_tenant(
    entidad: EntidadCampoLibre,
    datos: CampoLibreDefinicionCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> CampoLibreDefinicionOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        definicion = await service.crear_definicion(session, cuenta_id, entidad, datos)
    except service.ClaveDuplicada as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CampoLibreDefinicionOut.model_validate(definicion)


@definiciones_router.patch("/{entidad}/{definicion_id}", response_model=CampoLibreDefinicionOut)
async def actualizar_definicion_tenant(
    entidad: EntidadCampoLibre,
    definicion_id: uuid.UUID,
    datos: CampoLibreDefinicionUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> CampoLibreDefinicionOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        definicion = await service.actualizar_definicion(session, cuenta_id, entidad, definicion_id, datos)
    except service.DefinicionNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CampoLibreDefinicionOut.model_validate(definicion)


@definiciones_router.delete("/{entidad}/{definicion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_definicion_tenant(
    entidad: EntidadCampoLibre,
    definicion_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> None:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    if not await service.eliminar_definicion(session, cuenta_id, entidad, definicion_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campo no encontrado")


@valores_router.get("/definiciones/{entidad}", response_model=list[CampoLibreDefinicionOut])
async def listar_definiciones_activas(
    entidad: EntidadCampoLibre,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[CampoLibreDefinicionOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    definiciones = await service.listar_definiciones(session, cuenta_id, entidad, solo_activas=True)
    return [CampoLibreDefinicionOut.model_validate(d) for d in definiciones]


@valores_router.get("/{entidad}/{entidad_id}", response_model=dict[str, str | None])
async def obtener_valores(
    entidad: EntidadCampoLibre,
    entidad_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | None]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    # `cuenta_id_del_principal` ya habría lanzado 404 si `organization_id`
    # fuera None (personal de plataforma) — a partir de aquí siempre hay uno.
    assert principal.organization_id is not None
    return await service.obtener_valores(session, principal.organization_id, cuenta_id, entidad, entidad_id)


@valores_router.put("/{entidad}/{entidad_id}", response_model=dict[str, str | None])
async def establecer_valores(
    entidad: EntidadCampoLibre,
    entidad_id: uuid.UUID,
    datos: ValoresCampoLibreUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | None]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    assert principal.organization_id is not None
    await service.establecer_valores(session, principal.organization_id, cuenta_id, entidad, entidad_id, datos.valores)
    return await service.obtener_valores(session, principal.organization_id, cuenta_id, entidad, entidad_id)


router.include_router(definiciones_router)
router.include_router(valores_router)
