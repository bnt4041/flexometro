"""Bancos y cajas (Fase 44), en dos sabores como el diccionario:

- `router`: lectura de las activas, para cualquier usuario del tenant — lo
  necesita el formulario de cobro, no solo la pantalla de ajustes.
- `tenant_router`: el CRUD, gated por `require_admin_organizacion`.

No hace falta resolver ninguna cuenta ni organización a mano: estas filas van
por `organization_id` con RLS, así que la sesión ya las filtra sola.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_principal, require_admin_organizacion
from app.core.database import get_session
from app.modules.core import tesoreria_service as service
from app.modules.core.tesoreria_schemas import (
    CuentaFinancieraCreate,
    CuentaFinancieraOut,
    CuentaFinancieraUpdate,
)

router = APIRouter(
    prefix="/cuentas-financieras", tags=["tesorería"], dependencies=[Depends(get_principal)]
)
tenant_router = APIRouter(
    prefix="/ajustes/cuentas-financieras",
    tags=["ajustes"],
    dependencies=[Depends(require_admin_organizacion)],
)


@router.get("", response_model=list[CuentaFinancieraOut])
async def listar_activas(session: AsyncSession = Depends(get_session)) -> list[CuentaFinancieraOut]:
    cuentas = await service.listar(session, solo_activas=True)
    return [CuentaFinancieraOut.model_validate(c) for c in cuentas]


@tenant_router.get("", response_model=list[CuentaFinancieraOut])
async def listar_todas(session: AsyncSession = Depends(get_session)) -> list[CuentaFinancieraOut]:
    cuentas = await service.listar(session)
    return [CuentaFinancieraOut.model_validate(c) for c in cuentas]


@tenant_router.post("", response_model=CuentaFinancieraOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: CuentaFinancieraCreate, session: AsyncSession = Depends(get_session)
) -> CuentaFinancieraOut:
    try:
        cuenta = await service.crear(session, datos)
    except service.NombreDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CuentaFinancieraOut.model_validate(cuenta)


@tenant_router.patch("/{cuenta_id}", response_model=CuentaFinancieraOut)
async def actualizar(
    cuenta_id: uuid.UUID,
    datos: CuentaFinancieraUpdate,
    session: AsyncSession = Depends(get_session),
) -> CuentaFinancieraOut:
    try:
        cuenta = await service.actualizar(session, cuenta_id, datos)
    except service.CuentaNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.NombreDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CuentaFinancieraOut.model_validate(cuenta)


@tenant_router.delete("/{cuenta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> None:
    try:
        await service.eliminar(session, cuenta_id)
    except service.CuentaNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.CuentaEnUso as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
