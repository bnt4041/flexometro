"""Cliente de la API pública de tipos de cambio (Fase 23).

Frankfurter (https://www.frankfurter.app) republica los tipos de referencia
del Banco Central Europeo, en abierto y sin necesitar clave — encaja con que
esto es solo información de consulta, no algo que dependa de una cuenta de
pago de terceros para funcionar.
"""

import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.frankfurter.dev/v1"


class TipoDeCambioError(Exception):
    pass


async def obtener_tasas(codigos: list[str]) -> dict[str, Decimal]:
    """`codigos` en ISO 4217 (p.ej. `["USD", "GBP"]`). Devuelve cuántas
    unidades de cada moneda equivalen a 1 EUR — la misma convención que
    `Moneda.unidades_por_euro`."""
    if not codigos:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as cliente:
            respuesta = await cliente.get(
                f"{BASE_URL}/latest", params={"from": "EUR", "to": ",".join(codigos)}
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
    except httpx.HTTPError as exc:
        raise TipoDeCambioError(f"No se pudo consultar el tipo de cambio: {exc}") from exc

    tasas = datos.get("rates", {})
    return {codigo: Decimal(str(tasas[codigo])) for codigo in codigos if codigo in tasas}
