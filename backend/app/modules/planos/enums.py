from enum import StrEnum


class TipoElemento(StrEnum):
    """Todo lo que se dibuja encima de un plano vive en la misma tabla, como
    en un CAD: una nota y una medición no son cosas distintas, son entidades
    de tipos distintos sobre una capa."""

    #: Texto anclado a un punto.
    NOTA = "nota"
    #: Trazo de referencia. No mide: sirve para alinear y para replantear.
    AUXILIAR = "auxiliar"
    #: Polilínea cuya longitud real se calcula con la escala de la hoja.
    LONGITUD = "longitud"
    #: Polígono cerrado. Su área se calcula por la fórmula del zapatero.
    AREA = "area"
    #: Puntos sueltos que se cuentan (enchufes, luminarias, arquetas).
    CONTEO = "conteo"


#: Los tipos que producen un número. Los demás no tienen `valor` ni `unidad`,
#: y ponérselos sería inventarse una medición.
TIPOS_QUE_MIDEN = frozenset({TipoElemento.LONGITUD, TipoElemento.AREA, TipoElemento.CONTEO})

#: Unidad de cada tipo que mide. No es cosmética: es lo que se compara con la
#: unidad de la partida antes de dejar aplicar la medición.
UNIDAD_DE = {
    TipoElemento.LONGITUD: "m",
    TipoElemento.AREA: "m2",
    TipoElemento.CONTEO: "ud",
}


class OrigenPlano(StrEnum):
    """De qué se levantó la hoja. Decide cómo se calibra: un PDF vectorial
    trae sus propias dimensiones de página, una foto de un plano de papel no
    trae nada y hay que darle una cota conocida."""

    PDF = "pdf"
    IMAGEN = "imagen"
    #: Vectorial. Es el único que se puede medir con exactitud: no se estima
    #: dónde está la pared a ojo de píxel, se pincha la entidad.
    DXF = "dxf"
