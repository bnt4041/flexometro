"""Diccionario de referencia por cuenta (Fase 18), en dos sabores:

- `router`: lectura, para cualquier usuario autenticado de un tenant — lo
  necesitan los formularios normales de negocio (el país de un tercero, su
  forma de pago), no solo la pantalla de ajustes. Solo entradas activas.
- `tenant_router`: autoservicio de edición, gated por
  `require_admin_organizacion`, mismo patrón que `ajustes_router.py`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.database import get_session
from app.modules.core import diccionario_service
from app.modules.core.diccionario_models import TipoDiccionario
from app.modules.core.diccionario_schemas import (
    EntradaDiccionarioCreate,
    EntradaDiccionarioOut,
    EntradaDiccionarioUpdate,
)
from app.modules.core.tenant_utils import cuenta_id_del_principal

router = APIRouter(prefix="/diccionario", tags=["diccionario"])
tenant_router = APIRouter(
    prefix="/ajustes/diccionario",
    tags=["ajustes"],
    dependencies=[Depends(require_admin_organizacion)],
)


@router.get("/{tipo}", response_model=list[EntradaDiccionarioOut])
async def listar_entradas_activas(
    tipo: TipoDiccionario,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[EntradaDiccionarioOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    entradas = await diccionario_service.listar_entradas(session, cuenta_id, tipo, solo_activas=True)
    return [EntradaDiccionarioOut.model_validate(e) for e in entradas]


@tenant_router.get("/{tipo}", response_model=list[EntradaDiccionarioOut])
async def listar_entradas_tenant(
    tipo: TipoDiccionario,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[EntradaDiccionarioOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    entradas = await diccionario_service.listar_entradas(session, cuenta_id, tipo)
    return [EntradaDiccionarioOut.model_validate(e) for e in entradas]


@tenant_router.post("/{tipo}", response_model=EntradaDiccionarioOut, status_code=status.HTTP_201_CREATED)
async def crear_entrada_tenant(
    tipo: TipoDiccionario,
    datos: EntradaDiccionarioCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EntradaDiccionarioOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        entrada = await diccionario_service.crear_entrada(session, cuenta_id, tipo, datos)
    except diccionario_service.ClaveDuplicada as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EntradaDiccionarioOut.model_validate(entrada)


@tenant_router.patch("/{tipo}/{entrada_id}", response_model=EntradaDiccionarioOut)
async def actualizar_entrada_tenant(
    tipo: TipoDiccionario,
    entrada_id: uuid.UUID,
    datos: EntradaDiccionarioUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EntradaDiccionarioOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        entrada = await diccionario_service.actualizar_entrada(session, cuenta_id, entrada_id, datos)
    except diccionario_service.EntradaNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return EntradaDiccionarioOut.model_validate(entrada)


@tenant_router.delete("/{tipo}/{entrada_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_entrada_tenant(
    tipo: TipoDiccionario,
    entrada_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> None:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    if not await diccionario_service.eliminar_entrada(session, cuenta_id, entrada_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entrada no encontrada")
