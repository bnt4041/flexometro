"""Ejecutar un informe: agrupar, sumar y devolver filas.

Lo único que hay que mirar dos veces está en `_acotar`: el alcance de quien
pide el informe se aplica DENTRO de la consulta, no filtrando después. Un
agregado calculado sobre todo y recortado luego ya habría revelado el total
—que es justo lo que no puede ver—.
"""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import Alcance
from app.modules.informes.fuentes import Fuente

logger = logging.getLogger(__name__)

#: Tope de filas del resultado. Un informe con miles de grupos no se lee: se
#: filtra. El tope evita además mandar media base al navegador.
MAX_FILAS = 500


class InformeInvalido(Exception):
    pass


def _columna(fuente: Fuente, nombre: str):
    dimension = next((d for d in fuente.dimensiones if d.nombre == nombre), None)
    if dimension is None:
        raise InformeInvalido(f"«{nombre}» no es una dimensión de {fuente.etiqueta}")
    columna = dimension.columna()
    if dimension.tipo == "mes":
        # `date_trunc` y no `to_char`: agrupar por texto ordenaría
        # «2026-01» después de «2025-12» solo por casualidad alfabética, y
        # con dos años de datos el gráfico saldría desordenado.
        return func.date_trunc("month", columna)
    return columna


def _acotar(consulta, fuente: Fuente, alcance: Alcance, subject: str):
    """Mete el alcance DENTRO de la consulta."""
    if alcance != Alcance.PROPIOS:
        return consulta
    if not fuente.columna_autor:
        # La fuente no sabe de quién es cada fila. Enseñarla entera sería
        # saltarse el permiso; se niega, que es lo honesto.
        raise InformeInvalido(
            f"«{fuente.etiqueta}» no se puede consultar con permiso limitado a lo propio"
        )
    modelo = fuente.modelo()
    return consulta.where(getattr(modelo, fuente.columna_autor) == subject)


async def ejecutar(
    session: AsyncSession,
    fuente: Fuente,
    *,
    dimensiones: list[str],
    metricas: list[str],
    filtros: dict[str, str] | None,
    alcance: Alcance,
    subject: str,
    limite: int = MAX_FILAS,
) -> list[dict[str, Any]]:
    if not metricas:
        raise InformeInvalido("Un informe necesita al menos una métrica")

    modelo = fuente.modelo()
    columnas_dim = [_columna(fuente, d) for d in dimensiones]
    seleccionadas = list(columnas_dim)

    for nombre in metricas:
        metrica = next((m for m in fuente.metricas if m.nombre == nombre), None)
        if metrica is None:
            raise InformeInvalido(f"«{nombre}» no es una métrica de {fuente.etiqueta}")
        seleccionadas.append(metrica.agregado())

    consulta = select(*seleccionadas).select_from(modelo)
    consulta = _acotar(consulta, fuente, alcance, subject)

    for nombre, valor in (filtros or {}).items():
        if valor in (None, ""):
            continue
        # Comparación en texto: las dimensiones son enums, booleanos o
        # cadenas, y castear a texto vale para todas sin un `if` por tipo.
        consulta = consulta.where(func.cast(_columna(fuente, nombre), type_=None) == valor)

    if columnas_dim:
        consulta = consulta.group_by(*columnas_dim)
        # Por la primera métrica y de mayor a menor: en un informe lo que
        # interesa está arriba, no en orden alfabético.
        consulta = consulta.order_by(seleccionadas[len(columnas_dim)].desc())

    filas = (await session.execute(consulta.limit(limite))).all()

    salida = []
    for fila in filas:
        registro: dict[str, Any] = {}
        for i, nombre in enumerate(dimensiones):
            registro[nombre] = _presentable(fila[i])
        for j, nombre in enumerate(metricas):
            registro[nombre] = _presentable(fila[len(dimensiones) + j])
        salida.append(registro)
    return salida


def _presentable(valor: Any) -> Any:
    """A algo que viaje en JSON sin sorpresas."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        # Los importes van como número, no como cadena: el frontend los
        # formatea según la moneda y sumarlos como texto no funcionaría.
        return float(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if hasattr(valor, "value"):  # StrEnum
        return valor.value
    return valor
