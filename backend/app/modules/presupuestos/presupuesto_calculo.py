"""Cálculo del presupuesto: mediciones, importes y el encadenado PEM → PEC."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TIPO_IVA_PORCENTAJE
from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.presupuestos.models import Concepto
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    LineaMedicion,
    Partida,
    Presupuesto,
)


def parcial_de(
    uds: Decimal | None,
    longitud: Decimal | None,
    anchura: Decimal | None,
    altura: Decimal | None,
) -> Decimal:
    """Parcial de una línea de medición.

    Las dimensiones no informadas valen 1, no 0: una línea con solo `uds = 5`
    mide 5. Un cero explícito sí anula la línea, que es lo que se espera al
    teclear un 0 a propósito.
    """
    factores = [f for f in (uds, longitud, anchura, altura) if f is not None]
    if not factores:
        return Decimal("0.000")
    producto = Decimal("1")
    for factor in factores:
        producto *= factor
    return redondear_medicion(producto)


async def recalcular_partida(session: AsyncSession, partida: Partida) -> None:
    """Vuelve a sumar la medición y el importe de una partida."""
    filas = await session.execute(
        select(LineaMedicion.parcial).where(LineaMedicion.partida_id == partida.id)
    )
    total = sum((fila[0] for fila in filas.all()), Decimal("0.000"))
    partida.medicion = redondear_medicion(total)
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    await session.flush()


def _precio_del_cuadro():
    """Subconsulta escalar con el precio actual del concepto de cada partida."""
    return (
        select(Concepto.precio)
        .where(Concepto.id == Partida.concepto_id)
        .scalar_subquery()
    )


async def _traer_precios(session: AsyncSession, condiciones: list) -> int:
    precio_actual = _precio_del_cuadro()
    resultado = await session.execute(
        update(Partida)
        .where(
            Partida.concepto_id.is_not(None),
            Partida.precio != precio_actual,
            *condiciones,
        )
        .values(
            precio=precio_actual,
            importe=func.round(Partida.medicion * precio_actual, 2),
        )
    )
    return resultado.rowcount or 0


async def propagar_a_partidas(
    session: AsyncSession, conceptos_modificados: list[uuid.UUID]
) -> int:
    """Lleva el precio del cuadro a las partidas que lo usan.

    Solo alcanza a los presupuestos sin bloquear: uno emitido conserva el
    precio con el que se firmó. Es el último tramo de la cascada
    suministro → básico → auxiliar → unitario → partida.
    """
    if not conceptos_modificados:
        return 0

    org_id = require_organization_id()
    sin_bloquear = (
        select(Presupuesto.id)
        .where(
            Presupuesto.organization_id == org_id,
            Presupuesto.precios_bloqueados.is_(False),
        )
        .scalar_subquery()
    )
    return await _traer_precios(
        session,
        [
            Partida.organization_id == org_id,
            Partida.concepto_id.in_(conceptos_modificados),
            Partida.presupuesto_id.in_(sin_bloquear),
        ],
    )


async def partidas_desactualizadas(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[tuple[uuid.UUID, Decimal, Decimal]]:
    """Partidas cuyo precio ya no coincide con el del cuadro de precios.

    Solo puede pasar con los precios bloqueados: en los demás la cascada las
    mantiene al día. Devuelve (partida_id, precio en la partida, precio actual).
    """
    org_id = require_organization_id()
    filas = await session.execute(
        select(Partida.id, Partida.precio, Concepto.precio)
        .join(Concepto, Concepto.id == Partida.concepto_id)
        .where(
            Partida.presupuesto_id == presupuesto_id,
            Partida.organization_id == org_id,
            Partida.precio != Concepto.precio,
        )
        .order_by(Partida.orden)
    )
    return [(fila[0], fila[1], fila[2]) for fila in filas.all()]


async def sincronizar_precios(session: AsyncSession, presupuesto_id: uuid.UUID) -> int:
    """Trae los precios actuales del cuadro a un presupuesto, aunque esté
    bloqueado. Es una acción explícita, nunca automática."""
    org_id = require_organization_id()
    return await _traer_precios(
        session,
        [
            Partida.organization_id == org_id,
            Partida.presupuesto_id == presupuesto_id,
        ],
    )


# --- Totales ---


class Totales:
    """Encadenado clásico del presupuesto español.

    PEM (ejecución material) → + gastos generales + beneficio industrial
    → PEC sin IVA (ejecución por contrata) → + IVA → total.
    """

    def __init__(self, presupuesto: Presupuesto, pem: Decimal) -> None:
        self.pem = redondear_precio(pem)
        self.gastos_generales = redondear_precio(
            self.pem * presupuesto.gastos_generales / Decimal("100")
        )
        self.beneficio_industrial = redondear_precio(
            self.pem * presupuesto.beneficio_industrial / Decimal("100")
        )
        self.pec_sin_iva = self.pem + self.gastos_generales + self.beneficio_industrial

        porcentaje_iva = Decimal(TIPO_IVA_PORCENTAJE[presupuesto.tipo_iva])
        # Con inversión del sujeto pasivo la factura va sin IVA: lo
        # autorrepercute el destinatario.
        if presupuesto.inversion_sujeto_pasivo:
            porcentaje_iva = Decimal("0")
        self.porcentaje_iva = porcentaje_iva
        self.iva = redondear_precio(self.pec_sin_iva * porcentaje_iva / Decimal("100"))
        self.total = self.pec_sin_iva + self.iva

    def como_dict(self) -> dict:
        return {
            "pem": self.pem,
            "gastos_generales": self.gastos_generales,
            "beneficio_industrial": self.beneficio_industrial,
            "pec_sin_iva": self.pec_sin_iva,
            "porcentaje_iva": self.porcentaje_iva,
            "iva": self.iva,
            "total": self.total,
        }


async def cargar_estructura(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> tuple[list[Capitulo], list[Partida]]:
    """Capítulos y partidas del presupuesto, en dos consultas.

    Se carga entero y se agrega en memoria: un presupuesto tiene cientos de
    filas, no millones, y el árbol en Python se lee mucho mejor que una CTE
    recursiva con agregación ascendente.
    """
    org_id = require_organization_id()
    capitulos = (
        await session.execute(
            select(Capitulo)
            .where(
                Capitulo.presupuesto_id == presupuesto_id,
                Capitulo.organization_id == org_id,
            )
            .order_by(Capitulo.orden, Capitulo.codigo)
        )
    ).scalars()
    partidas = (
        await session.execute(
            select(Partida)
            .where(
                Partida.presupuesto_id == presupuesto_id,
                Partida.organization_id == org_id,
            )
            .order_by(Partida.orden, Partida.codigo)
        )
    ).scalars()
    return list(capitulos), list(partidas)


def importes_por_capitulo(
    capitulos: list[Capitulo], partidas: list[Partida]
) -> dict[uuid.UUID, Decimal]:
    """Importe acumulado de cada capítulo, incluidos sus subcapítulos."""
    directo: dict[uuid.UUID, Decimal] = {c.id: Decimal("0.00") for c in capitulos}
    for partida in partidas:
        if partida.capitulo_id in directo:
            directo[partida.capitulo_id] += partida.importe

    hijos: dict[uuid.UUID | None, list[Capitulo]] = {}
    for capitulo in capitulos:
        hijos.setdefault(capitulo.parent_id, []).append(capitulo)

    acumulado: dict[uuid.UUID, Decimal] = {}

    def sumar(capitulo: Capitulo) -> Decimal:
        if capitulo.id in acumulado:
            return acumulado[capitulo.id]
        total = directo[capitulo.id]
        for hijo in hijos.get(capitulo.id, []):
            total += sumar(hijo)
        acumulado[capitulo.id] = redondear_precio(total)
        return acumulado[capitulo.id]

    for capitulo in capitulos:
        sumar(capitulo)
    return acumulado


def pem_de(capitulos: list[Capitulo], acumulado: dict[uuid.UUID, Decimal]) -> Decimal:
    """El PEM es la suma de los capítulos raíz; sumar todos contaría dos veces
    los subcapítulos."""
    return redondear_precio(
        sum(
            (acumulado[c.id] for c in capitulos if c.parent_id is None),
            Decimal("0.00"),
        )
    )
