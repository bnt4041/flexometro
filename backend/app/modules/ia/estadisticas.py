"""Estadísticas propias sobre el histórico de presupuestos.

Nada de esto llama a ningún modelo: es pura agregación SQL sobre los
presupuestos de la organización (reales y plantillas), autoalojada y
determinista. Es el terreno firme sobre el que luego DeepSeek propone una
síntesis — así, si la IA no está configurada o falla, esto sigue siendo útil
por sí solo.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import require_organization_id
from app.modules.presupuestos.models_presupuesto import Capitulo, Partida, Presupuesto

MAX_CAPITULOS = 15
MAX_PARTIDAS = 30


@dataclass
class CapituloFrecuente:
    resumen: str
    veces: int


@dataclass
class PartidaFrecuente:
    concepto_id: uuid.UUID
    codigo: str
    resumen: str
    unidad: str
    veces: int


@dataclass
class Estadisticas:
    # True si no había histórico específico de este tipo_obra y se ha caído
    # a mirar todos los presupuestos de la organización.
    generico: bool
    total_presupuestos: int
    capitulos: list[CapituloFrecuente] = field(default_factory=list)
    partidas: list[PartidaFrecuente] = field(default_factory=list)


def _agregar(
    filas_capitulos: list[tuple[str]],
    filas_partidas: list[tuple[uuid.UUID, str, str, str]],
    *,
    total_presupuestos: int,
    generico: bool,
) -> Estadisticas:
    conteo_capitulos: dict[str, int] = {}
    etiqueta_capitulos: dict[str, str] = {}
    for (resumen,) in filas_capitulos:
        clave = resumen.strip().lower()
        conteo_capitulos[clave] = conteo_capitulos.get(clave, 0) + 1
        etiqueta_capitulos.setdefault(clave, resumen.strip())

    conteo_partidas: dict[uuid.UUID, int] = {}
    datos_partidas: dict[uuid.UUID, tuple[str, str, str]] = {}
    for concepto_id, codigo, resumen, unidad in filas_partidas:
        conteo_partidas[concepto_id] = conteo_partidas.get(concepto_id, 0) + 1
        datos_partidas[concepto_id] = (codigo, resumen, unidad)

    capitulos = sorted(
        (
            CapituloFrecuente(resumen=etiqueta_capitulos[clave], veces=veces)
            for clave, veces in conteo_capitulos.items()
        ),
        key=lambda c: -c.veces,
    )[:MAX_CAPITULOS]

    partidas = sorted(
        (
            PartidaFrecuente(
                concepto_id=concepto_id,
                codigo=datos_partidas[concepto_id][0],
                resumen=datos_partidas[concepto_id][1],
                unidad=datos_partidas[concepto_id][2],
                veces=veces,
            )
            for concepto_id, veces in conteo_partidas.items()
        ),
        key=lambda p: -p.veces,
    )[:MAX_PARTIDAS]

    return Estadisticas(
        generico=generico,
        total_presupuestos=total_presupuestos,
        capitulos=capitulos,
        partidas=partidas,
    )


async def _presupuestos_relevantes(
    session: AsyncSession, org_id: uuid.UUID, tipo_obra: str | None
) -> tuple[list[uuid.UUID], bool]:
    if tipo_obra:
        filas = await session.execute(
            select(Presupuesto.id).where(
                Presupuesto.organization_id == org_id,
                Presupuesto.tipo_obra.is_not(None),
                Presupuesto.tipo_obra.ilike(tipo_obra.strip()),
            )
        )
        ids = [fila[0] for fila in filas.all()]
        if ids:
            return ids, False

    # Sin histórico de este tipo de obra concreto: mejor una síntesis genérica
    # de todo lo que hay que no proponer nada.
    todos = await session.execute(
        select(Presupuesto.id).where(Presupuesto.organization_id == org_id)
    )
    return [fila[0] for fila in todos.all()], True


async def calcular_estadisticas(
    session: AsyncSession, tipo_obra: str | None
) -> Estadisticas:
    org_id = require_organization_id()
    ids, generico = await _presupuestos_relevantes(session, org_id, tipo_obra)
    if not ids:
        return Estadisticas(generico=generico, total_presupuestos=0)

    filas_capitulos = (
        await session.execute(
            select(Capitulo.resumen).where(Capitulo.presupuesto_id.in_(ids))
        )
    ).all()
    filas_partidas = (
        await session.execute(
            select(Partida.concepto_id, Partida.codigo, Partida.resumen, Partida.unidad).where(
                Partida.presupuesto_id.in_(ids), Partida.concepto_id.is_not(None)
            )
        )
    ).all()

    return _agregar(
        filas_capitulos,
        filas_partidas,
        total_presupuestos=len(ids),
        generico=generico,
    )
