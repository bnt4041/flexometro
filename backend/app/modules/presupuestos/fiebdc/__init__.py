"""Interoperabilidad con FIEBDC-3 (ficheros BC3).

Es el formato con el que se mueven en España los bancos de precios oficiales
(BEDEC, autonómicos) y los presupuestos entre Presto, Arquímedes y TCQ. Sin
esto, nadie puede traerse aquí lo que ya tiene.

    lector    -> bytes a registros, resolviendo la codificación
    parser    -> registros al modelo intermedio, sin tocar la base de datos
    importador-> modelo intermedio a conceptos, presupuesto y mediciones
    exportador-> presupuesto a fichero BC3
"""

from app.modules.presupuestos.fiebdc.exportador import exportar_presupuesto
from app.modules.presupuestos.fiebdc.importador import (
    EstrategiaCodigos,
    ResultadoImportacion,
    importar,
    importar_bajo_capitulo,
    importar_en_raiz,
)
from app.modules.presupuestos.fiebdc.parser import parsear

__all__ = [
    "EstrategiaCodigos",
    "ResultadoImportacion",
    "exportar_presupuesto",
    "importar",
    "importar_bajo_capitulo",
    "importar_en_raiz",
    "parsear",
]
