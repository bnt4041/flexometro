"""Documentos PDF del presupuesto.

Se componen con Jinja2 y se rasterizan con WeasyPrint dentro del contenedor: no
hay servicio externo de por medio y las plantillas son HTML+CSS editables, así
que ajustar el papel no obliga a tocar código Python.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenancy import require_organization_id
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos import service as service_conceptos
from app.modules.presupuestos.models import Concepto, Descomposicion
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    LineaMedicion,
    Partida,
    Presupuesto,
)

DIRECTORIO_PLANTILLAS = Path(__file__).parent / "plantillas"

DOCUMENTOS = {
    "presupuesto": ("presupuesto.html", "Presupuesto"),
    "mediciones": ("mediciones.html", "Estado de mediciones"),
    "descompuestos": ("descompuestos.html", "Cuadro de precios descompuestos"),
}


def _formato_es(valor: Any, decimales: int) -> str:
    """Número en formato español: punto de millares y coma decimal."""
    if valor is None:
        return ""
    numero = Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales))
    entero, _, fraccion = f"{abs(numero):.{decimales}f}".partition(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    texto = ".".join(grupos)
    if decimales:
        texto = f"{texto},{fraccion}"
    return f"-{texto}" if numero < 0 else texto


def _entorno() -> Environment:
    entorno = Environment(
        loader=FileSystemLoader(DIRECTORIO_PLANTILLAS),
        autoescape=select_autoescape(["html"]),
    )
    entorno.filters["eur"] = lambda v: _formato_es(v, 2)
    entorno.filters["num"] = _formato_es
    return entorno


@dataclass
class NodoInforme:
    codigo: str
    resumen: str
    importe: Decimal
    partidas: list[Any]
    hijos: list["NodoInforme"]


async def _cliente_de(session: AsyncSession, presupuesto: Presupuesto):
    if presupuesto.cliente_id is None:
        return None
    from app.modules.terceros.models import Tercero

    return await session.scalar(
        select(Tercero).where(Tercero.id == presupuesto.cliente_id)
    )


async def _arbol(
    session: AsyncSession, presupuesto_id: uuid.UUID, *, con_mediciones: bool
) -> list[NodoInforme]:
    """Árbol de capítulos con sus partidas, opcionalmente con las líneas de
    medición cargadas."""
    org_id = require_organization_id()
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto_id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)

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

    por_capitulo: dict[uuid.UUID, list[Any]] = {}
    for partida in partidas:
        # Se adjuntan las líneas como atributo transitorio para que la
        # plantilla las recorra sin una consulta por partida.
        partida.lineas_informe = lineas_por_partida.get(partida.id, [])
        por_capitulo.setdefault(partida.capitulo_id, []).append(partida)

    hijos: dict[uuid.UUID | None, list[Capitulo]] = {}
    for capitulo in capitulos:
        hijos.setdefault(capitulo.parent_id, []).append(capitulo)

    def construir(capitulo: Capitulo) -> NodoInforme:
        return NodoInforme(
            codigo=capitulo.codigo,
            resumen=capitulo.resumen,
            importe=acumulado[capitulo.id],
            partidas=por_capitulo.get(capitulo.id, []),
            hijos=[construir(h) for h in hijos.get(capitulo.id, [])],
        )

    return [construir(c) for c in hijos.get(None, [])]


async def _conceptos_del_presupuesto(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[Any]:
    """Unitarios usados por el presupuesto, con su descomposición resuelta."""
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


async def generar(
    session: AsyncSession, presupuesto: Presupuesto, documento: str
) -> bytes:
    """Devuelve el PDF del documento pedido."""
    from weasyprint import HTML

    plantilla_nombre, titulo = DOCUMENTOS[documento]
    cliente = await _cliente_de(session, presupuesto)

    contexto: dict[str, Any] = {
        "presupuesto": presupuesto,
        "cliente": cliente,
        "titulo": titulo,
    }

    if documento == "descompuestos":
        conceptos = await _conceptos_del_presupuesto(session, presupuesto.id)
        # La plantilla itera `concepto.lineas`, así que se le pasa la
        # proyección con los datos del hijo ya resueltos.
        contexto["conceptos"] = [
            {
                "codigo": c.codigo,
                "resumen": c.resumen,
                "texto": c.texto,
                "unidad": c.unidad,
                "precio": c.precio,
                "costes_indirectos": c.costes_indirectos,
                "coste_directo": c.coste_directo,
                "lineas": c.lineas_informe,
            }
            for c in conceptos
        ]
    else:
        con_mediciones = documento == "mediciones"
        nodos = await _arbol(session, presupuesto.id, con_mediciones=con_mediciones)
        contexto["capitulos"] = _serializar(nodos)
        if documento == "presupuesto":
            _, totales = await _totales(session, presupuesto)
            contexto["totales"] = totales

    html = _entorno().get_template(plantilla_nombre).render(**contexto)
    return HTML(string=html).write_pdf()


def _serializar(nodos: list[NodoInforme]) -> list[dict]:
    return [
        {
            "codigo": nodo.codigo,
            "resumen": nodo.resumen,
            "importe": nodo.importe,
            "partidas": [
                {
                    "codigo": p.codigo,
                    "resumen": p.resumen,
                    "texto": p.texto,
                    "unidad": p.unidad,
                    "medicion": p.medicion,
                    "precio": p.precio,
                    "importe": p.importe,
                    "lineas": getattr(p, "lineas_informe", []),
                }
                for p in nodo.partidas
            ],
            "hijos": _serializar(nodo.hijos),
        }
        for nodo in nodos
    ]


async def _totales(session: AsyncSession, presupuesto: Presupuesto):
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto.id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
    pem = calc.pem_de(capitulos, acumulado)
    return pem, calc.Totales(presupuesto, pem).como_dict()
