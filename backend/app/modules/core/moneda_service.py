import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core import moneda_cliente
from app.modules.core.moneda_models import Moneda

logger = logging.getLogger(__name__)

ANTIGUEDAD_MAXIMA = timedelta(hours=24)


async def listar_monedas(session: AsyncSession, *, refrescar_si_caducado: bool = True) -> list[Moneda]:
    monedas = list((await session.execute(select(Moneda).order_by(Moneda.codigo))).scalars())
    if refrescar_si_caducado and _hay_alguna_caducada(monedas):
        try:
            await actualizar_tasas_cambio(session)
        except moneda_cliente.TipoDeCambioError:
            logger.warning("No se pudieron refrescar los tipos de cambio; se sirven los últimos conocidos")
        else:
            monedas = list((await session.execute(select(Moneda).order_by(Moneda.codigo))).scalars())
    return monedas


def _hay_alguna_caducada(monedas: list[Moneda]) -> bool:
    ahora = datetime.now(UTC)
    for moneda in monedas:
        if moneda.codigo == "EUR":
            continue
        if moneda.actualizado_en is None or ahora - moneda.actualizado_en > ANTIGUEDAD_MAXIMA:
            return True
    return False


async def actualizar_tasas_cambio(session: AsyncSession) -> list[Moneda]:
    monedas = list((await session.execute(select(Moneda))).scalars())
    codigos = [m.codigo for m in monedas if m.codigo != "EUR"]
    tasas = await moneda_cliente.obtener_tasas(codigos)

    ahora = datetime.now(UTC)
    for moneda in monedas:
        if moneda.codigo in tasas:
            moneda.unidades_por_euro = tasas[moneda.codigo]
            moneda.actualizado_en = ahora
    await session.flush()
    return monedas
