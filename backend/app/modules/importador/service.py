"""Validar y ejecutar una importación."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import require_organization_id
from app.modules.importador import destinos
from app.modules.importador.enums import EstadoImportacion
from app.modules.importador.models import Importacion

#: Cuántas filas se enseñan en la vista previa. Suficiente para ver si el
#: mapeo es el bueno sin mandar la hoja entera al navegador.
FILAS_VISTA_PREVIA = 20


async def obtener(session: AsyncSession, importacion_id: uuid.UUID) -> Importacion | None:
    return await session.scalar(
        select(Importacion).where(
            Importacion.id == importacion_id,
            Importacion.organization_id == require_organization_id(),
        )
    )


def _preparar_fila(destino: destinos.Destino, fila: dict, mapeo: dict) -> dict:
    """Los datos de una fila ya convertidos. Lanza `FilaInvalida` si no vale."""
    datos = {}
    for campo in destino.campos:
        columna = mapeo.get(campo.nombre)
        crudo = fila.get(columna) if columna else None
        valor = destinos.convertir(crudo, campo)
        if valor is not None:
            datos[campo.nombre] = valor
    return datos


def validar(importacion: Importacion) -> list[dict]:
    """Repasa la hoja SIN escribir nada. Devuelve un problema por fila mala.

    Solo comprueba lo que se puede saber sin tocar la base: campos que faltan
    y valores que no se convierten. Un duplicado o un tercero que no existe
    solo salen al ejecutar, y por eso el resultado real puede traer más
    errores que esta vista previa — se dice en la pantalla.
    """
    destino = destinos.obtener(importacion.destino)
    if destino is None:
        return [{"fila": 0, "detalle": f"Destino desconocido: {importacion.destino}"}]

    problemas = []
    for numero, fila in enumerate(importacion.filas or [], start=1):
        try:
            _preparar_fila(destino, fila, importacion.mapeo or {})
        except destinos.FilaInvalida as exc:
            problemas.append({"fila": numero, "detalle": str(exc)})
    return problemas


async def ejecutar(session: AsyncSession, importacion: Importacion) -> Importacion:
    """Importa fila a fila.

    Cada fila va en su propio `SAVEPOINT`: si la 40 falla, las 39 anteriores
    quedan. Sin eso, un NIF repetido en la última línea tiraría abajo el
    trabajo entero — que es exactamente lo que hace inservible a un
    importador.
    """
    destino = destinos.obtener(importacion.destino)
    creador = destinos.creador_de(importacion.destino)
    if destino is None or creador is None:
        importacion.estado = EstadoImportacion.FALLIDA
        importacion.error = f"Destino desconocido: {importacion.destino}"
        await session.flush()
        return importacion

    resultado: list[dict] = []
    creadas = 0
    for numero, fila in enumerate(importacion.filas or [], start=1):
        try:
            datos = _preparar_fila(destino, fila, importacion.mapeo or {})
        except destinos.FilaInvalida as exc:
            resultado.append({"fila": numero, "estado": "error", "detalle": str(exc)})
            continue

        try:
            async with session.begin_nested():
                descripcion = await creador(session, datos)
        except destinos.FilaInvalida as exc:
            resultado.append({"fila": numero, "estado": "error", "detalle": str(exc)})
        except Exception as exc:  # noqa: BLE001
            # Ancho: cualquier cosa que reviente en una fila es problema de
            # ESA fila. El savepoint ya la ha deshecho.
            resultado.append({"fila": numero, "estado": "error", "detalle": str(exc)[:300]})
        else:
            resultado.append({"fila": numero, "estado": "ok", "detalle": descripcion})
            creadas += 1

    con_error = len(resultado) - creadas
    importacion.resultado = resultado
    importacion.creadas = creadas
    importacion.con_error = con_error
    importacion.estado = (
        EstadoImportacion.COMPLETADA
        if con_error == 0
        else EstadoImportacion.PARCIAL
        if creadas
        else EstadoImportacion.FALLIDA
    )
    importacion.ejecutada_en = datetime.now(UTC)
    await session.flush()
    return importacion
