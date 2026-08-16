"""Suscripciones de presupuestos a lo que pasa en otros módulos."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import PRECIO_SUMINISTRO_CAMBIADO, bus
from app.modules.presupuestos.calculo import recalcular_por_producto


async def _al_cambiar_tarifa(session: AsyncSession, producto_id: uuid.UUID) -> None:
    """Cambiar el precio de suministro propaga a los básicos que lo usan y,
    desde ellos, a auxiliares, unitarios y partidas."""
    await recalcular_por_producto(session, producto_id)


def registrar() -> None:
    bus.subscribe(PRECIO_SUMINISTRO_CAMBIADO, _al_cambiar_tarifa)
