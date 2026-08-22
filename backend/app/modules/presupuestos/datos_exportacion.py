"""Datos del presupuesto listos para exportar, en forma plana.

Punto único de donde salen los datos para el Excel y para el contexto de las
plantillas Word: capítulos y partidas en listas planas (no en árbol, porque
una tabla de Word con bucles no maneja bien la recursión), cliente, totales y
el cuadro de precios descompuesto — todo reutilizando los mismos cálculos que
ya usaba `informes.py` antes de retirarse en favor de las plantillas.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenancy import require_organization_id
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos import service as service_conceptos
from app.modules.presupuestos.models import Concepto, Descomposicion
from app.modules.presupuestos.models_presupuesto import LineaMedicion, Partida, Presupuesto


@dataclass
class CapituloPlano:
    codigo: str
    resumen: str
    importe: Decimal
    importe_venta: Decimal


@dataclass
class PartidaPlana:
    capitulo_codigo: str
    capitulo_resumen: str
    codigo: str
    resumen: str
    texto: str
    unidad: str
    medicion: Decimal
    precio: Decimal
    precio_venta: Decimal
    importe: Decimal
    importe_venta: Decimal
    lineas_medicion: list[LineaMedicion]


async def cliente_de(session: AsyncSession, presupuesto: Presupuesto) -> Any | None:
    if presupuesto.cliente_id is None:
        return None
    from app.modules.terceros.models import Tercero

    return await session.scalar(select(Tercero).where(Tercero.id == presupuesto.cliente_id))


async def capitulos_y_partidas_planos(
    session: AsyncSession, presupuesto_id: uuid.UUID, *, con_mediciones: bool = False
) -> tuple[list[CapituloPlano], list[PartidaPlana]]:
    """Capítulos y partidas del presupuesto, aplanados y con el nombre del
    capítulo ya resuelto en cada partida (útil para una fila de Excel o de
    tabla de Word, que no pueden recorrer un árbol)."""
    org_id = require_organization_id()
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto_id)
    acumulado_coste = calc.importes_por_capitulo(capitulos, partidas)
    acumulado_venta = calc.importes_por_capitulo(capitulos, partidas, lambda p: p.importe_venta)

    lineas_por_partida: dict[uuid.UUID, list[LineaMedicion]] = {}
    if con_mediciones:
        filas = await session.execute(
            select(LineaMedicion)
            .join(Partida, Partida.id == LineaMedicion.partida_id)
            .where(
                Partida.presupuesto_id == presupuesto_id,
                LineaMedicion.organization_id == org_id,
            )
            .order_by(LineaMedicion.orden)
        )
        for linea in filas.scalars():
            lineas_por_partida.setdefault(linea.partida_id, []).append(linea)

    nombre_capitulo = {c.id: c.codigo for c in capitulos}
    resumen_capitulo = {c.id: c.resumen for c in capitulos}

    capitulos_planos = [
        CapituloPlano(
            codigo=c.codigo,
            resumen=c.resumen,
            importe=acumulado_coste[c.id],
            importe_venta=acumulado_venta[c.id],
        )
        for c in capitulos
    ]
    partidas_planas = [
        PartidaPlana(
            capitulo_codigo=nombre_capitulo.get(p.capitulo_id, ""),
            capitulo_resumen=resumen_capitulo.get(p.capitulo_id, ""),
            codigo=p.codigo,
            resumen=p.resumen,
            texto=p.texto or "",
            unidad=p.unidad,
            medicion=p.medicion,
            precio=p.precio,
            precio_venta=p.precio_venta,
            importe=p.importe,
            importe_venta=p.importe_venta,
            lineas_medicion=lineas_por_partida.get(p.id, []),
        )
        for p in partidas
    ]
    return capitulos_planos, partidas_planas


async def conceptos_del_presupuesto(session: AsyncSession, presupuesto_id: uuid.UUID) -> list[Any]:
    """Conceptos unitarios usados por el presupuesto, con su descomposición
    resuelta — igual que el antiguo PDF de descompuestos."""
    org_id = require_organization_id()
    ids = (
        await session.execute(
            select(Partida.concepto_id)
            .where(
                Partida.presupuesto_id == presupuesto_id,
                Partida.concepto_id.is_not(None),
                Partida.organization_id == org_id,
            )
            .distinct()
        )
    ).scalars()
    ids = [i for i in ids if i is not None]
    if not ids:
        return []

    conceptos = (
        await session.execute(
            select(Concepto)
            .options(selectinload(Concepto.lineas).selectinload(Descomposicion.hijo))
            .where(Concepto.id.in_(ids), Concepto.organization_id == org_id)
            .order_by(Concepto.codigo)
        )
    ).scalars()

    resultado = []
    for concepto in conceptos:
        lineas = service_conceptos.lineas_de(concepto)
        concepto.lineas_informe = lineas
        concepto.coste_directo = service_conceptos.coste_directo_de(lineas)
        resultado.append(concepto)
    return resultado


async def totales_de(session: AsyncSession, presupuesto: Presupuesto) -> dict:
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto.id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
    pem = calc.pem_de(capitulos, acumulado)
    return calc.Totales(presupuesto, pem, calc.venta_total(partidas)).como_dict()
