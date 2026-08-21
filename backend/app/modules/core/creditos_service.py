"""Créditos IA (Fase 38): traduce el consumo real de IA (tokens de DeepSeek y
Gemini, con precios muy distintos entre sí — ver `Tarifa`) a una única
unidad que un usuario final entiende sin tener que saber qué proveedor
atendió cada llamada.

1 crédito vale siempre `Tarifa.valor_credito_euros`, así que el cálculo es
el mismo coste en euros que ya usa `billing_service.calcular_coste_mensual`
para la IA, solo que expresado en créditos en vez de en €. Reutiliza
`billing_service.tokens_del_mes_de_cuenta`, no vuelve a sumar `UsoIA` a
mano.
"""

import math
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core import billing_service, cuenta_service


@dataclass
class CreditosIAResumen:
    consumidos: int
    incluidos: int
    # None si la cuenta no tiene tarifa asignada: no hay con qué convertir
    # tokens a créditos, así que tampoco tiene sentido mostrar una cuota.
    sin_tarifa: bool


async def creditos_ia_del_mes(session: AsyncSession, cuenta_id: uuid.UUID) -> CreditosIAResumen:
    cuenta = await cuenta_service.obtener_cuenta(session, cuenta_id)
    if cuenta is None or cuenta.tarifa_id is None:
        return CreditosIAResumen(consumidos=0, incluidos=0, sin_tarifa=True)

    tarifa = await billing_service.obtener_tarifa(session, cuenta.tarifa_id)
    if tarifa is None or tarifa.valor_credito_euros <= 0:
        return CreditosIAResumen(consumidos=0, incluidos=0, sin_tarifa=True)

    tokens_deepseek, tokens_gemini = await billing_service.tokens_del_mes_de_cuenta(
        session, cuenta_id
    )
    coste_euros = (
        Decimal(tokens_deepseek) / Decimal("1000") * tarifa.precio_1000_tokens_deepseek
        + Decimal(tokens_gemini) / Decimal("1000") * tarifa.precio_1000_tokens_gemini
    )
    # Redondeo hacia arriba: un consumo minúsculo pero real ("0.2 créditos")
    # no debe leerse como "0 créditos, no ha gastado nada".
    consumidos = math.ceil(coste_euros / tarifa.valor_credito_euros)

    return CreditosIAResumen(
        consumidos=consumidos,
        incluidos=tarifa.creditos_ia_incluidos_mes,
        sin_tarifa=False,
    )
