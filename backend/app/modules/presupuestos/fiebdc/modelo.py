"""Modelo intermedio de un fichero BC3.

Se parsea a estas estructuras antes de tocar la base de datos. Separar las dos
cosas permite validar y diagnosticar un fichero sin escribir nada, y hace que
el importador no tenga que entender el formato.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class TipoConceptoBC3(StrEnum):
    """Clasificación deducida de la estructura del árbol, no del sufijo.

    La norma usa sufijos en el código (`##` raíz, `#` capítulo) y esa parte se
    aprovecha, pero para distinguir básico de auxiliar y de unitario manda la
    estructura: quién descompone a quién. Es más fiable que confiar en que
    todos los bancos respeten las convenciones de código, cosa que no hacen.
    """

    RAIZ = "raiz"
    CAPITULO = "capitulo"
    UNITARIO = "unitario"
    AUXILIAR = "auxiliar"
    BASICO = "basico"


# Campo TIPO del registro ~C: naturaleza del recurso.
NATURALEZA_FIEBDC = {
    "0": "sin_clasificar",
    "1": "mano_obra",
    "2": "maquinaria",
    "3": "material",
    "4": "residuo",
}


@dataclass
class ConceptoBC3:
    codigo: str
    unidad: str = ""
    resumen: str = ""
    precio: Decimal = Decimal("0")
    fecha: date | None = None
    # Valor crudo del campo TIPO de ~C, sin interpretar.
    tipo_fiebdc: str = ""
    texto: str | None = None
    tipo: TipoConceptoBC3 = TipoConceptoBC3.BASICO

    @property
    def naturaleza(self) -> str:
        return NATURALEZA_FIEBDC.get(self.tipo_fiebdc, "sin_clasificar")


@dataclass
class LineaDescomposicion:
    hijo: str
    factor: Decimal = Decimal("1")
    rendimiento: Decimal = Decimal("0")


@dataclass
class LineaMedicion:
    comentario: str = ""
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


@dataclass
class Medicion:
    padre: str
    hijo: str
    total: Decimal | None = None
    lineas: list[LineaMedicion] = field(default_factory=list)


@dataclass
class Incidencia:
    """Algo que el fichero trae y no se ha podido usar tal cual.

    No se aborta la importación por ellas: un BC3 real casi siempre tiene
    alguna, y es más útil importar lo que se entiende y listar el resto.
    """

    linea: int
    registro: str
    detalle: str


@dataclass
class ArchivoBC3:
    version: str = ""
    fecha: str = ""
    programa: str = ""
    cabecera: str = ""
    codificacion: str = ""
    conceptos: dict[str, ConceptoBC3] = field(default_factory=dict)
    descomposiciones: dict[str, list[LineaDescomposicion]] = field(default_factory=dict)
    mediciones: list[Medicion] = field(default_factory=list)
    incidencias: list[Incidencia] = field(default_factory=list)

    @property
    def raiz(self) -> ConceptoBC3 | None:
        for concepto in self.conceptos.values():
            if concepto.tipo is TipoConceptoBC3.RAIZ:
                return concepto
        return None

    @property
    def es_presupuesto(self) -> bool:
        """Un fichero con raíz y capítulos es una obra; sin ellos, un banco de
        precios."""
        return self.raiz is not None and any(
            c.tipo is TipoConceptoBC3.CAPITULO for c in self.conceptos.values()
        )

    def resumen_por_tipo(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for concepto in self.conceptos.values():
            conteo[concepto.tipo.value] = conteo.get(concepto.tipo.value, 0) + 1
        return conteo
