"""Créditos IA (Fase 38): autoservicio para CUALQUIER usuario autenticado de
la organización, no solo el admin — es información de consumo, no de
facturación (eso sigue siendo `billing_router`, solo para superadmin)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.modules.core import creditos_service
from app.modules.core.creditos_schemas import CreditosIAOut
from app.modules.core.tenant_utils import cuenta_id_del_principal

router = APIRouter(prefix="/creditos-ia", tags=["core"])


@router.get("", response_model=CreditosIAOut)
async def obtener_creditos_ia(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> CreditosIAOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    resumen = await creditos_service.creditos_ia_del_mes(session, cuenta_id)
    return CreditosIAOut(
        consumidos=resumen.consumidos,
        incluidos=resumen.incluidos,
        sin_tarifa=resumen.sin_tarifa,
    )
