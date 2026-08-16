"""Monedas y tipo de cambio (Fase 23): lectura para cualquier usuario
autenticado (se refresca sola si el dato lleva más de 24h, ver
`moneda_service.listar_monedas`), y un botón de "actualizar ahora"
autoservicio — es información pública y compartida por toda la plataforma,
así que cualquier admin de organización puede disparar el refresco sin que
eso le dé acceso a nada de otra cuenta.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin_organizacion
from app.core.database import get_session
from app.modules.core import moneda_cliente, moneda_service
from app.modules.core.moneda_schemas import MonedaOut

router = APIRouter(prefix="/monedas", tags=["monedas"])
tenant_router = APIRouter(
    prefix="/ajustes/monedas", tags=["ajustes"], dependencies=[Depends(require_admin_organizacion)]
)


@router.get("", response_model=list[MonedaOut])
async def listar_monedas(session: AsyncSession = Depends(get_session)) -> list[MonedaOut]:
    monedas = await moneda_service.listar_monedas(session)
    return [MonedaOut.model_validate(m) for m in monedas]


@tenant_router.post("/actualizar", response_model=list[MonedaOut])
async def actualizar_monedas(session: AsyncSession = Depends(get_session)) -> list[MonedaOut]:
    try:
        monedas = await moneda_service.actualizar_tasas_cambio(session)
    except moneda_cliente.TipoDeCambioError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [MonedaOut.model_validate(m) for m in monedas]
