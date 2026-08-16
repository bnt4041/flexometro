"""Enumeraciones compartidas entre módulos.

Se almacenan como VARCHAR con CHECK constraint (`native_enum=False`), no como
tipos ENUM nativos de PostgreSQL: añadir un valor es entonces una migración que
sustituye la constraint, y no un `ALTER TYPE` que en Postgres no se puede
revertir dentro de una transacción.
"""

from enum import StrEnum

import sqlalchemy as sa


class OrigenDato(StrEnum):
    """Trazabilidad del origen del dato.

    Principio de diseño: todo precio, producto o partida debe poder declarar de
    dónde salió, para poder auditar y filtrar lo generado automáticamente
    cuando lleguen la importación FIEBDC-3 y los componentes de IA.
    """

    MANUAL = "manual"
    FIEBDC3 = "fiebdc3"
    IA = "ia"
    IMPORTADO = "importado"


class Alcance(StrEnum):
    """Cuánto puede ver/editar un grupo de un módulo: nada, solo lo que creó
    el propio usuario, o todo lo de la organización. El orden importa —
    `app.core.permisos` lo usa para quedarse con el más amplio cuando un
    usuario pertenece a varios grupos con distinto alcance del mismo módulo."""

    NINGUNO = "ninguno"
    PROPIOS = "propios"
    TODOS = "todos"


class TipoPersona(StrEnum):
    FISICA = "fisica"
    JURIDICA = "juridica"


class TipoProducto(StrEnum):
    """Naturaleza del recurso.

    Coincide deliberadamente con la clasificación de FIEBDC-3 (mano de obra,
    maquinaria, materiales), para que la importación de bancos de precios no
    tenga que inventar un mapeo.
    """

    MATERIAL = "material"
    MANO_OBRA = "mano_obra"
    MAQUINARIA = "maquinaria"
    SERVICIO = "servicio"
    OTRO = "otro"


class TipoIVA(StrEnum):
    GENERAL = "general"  # 21 %
    REDUCIDO = "reducido"  # 10 %
    SUPERREDUCIDO = "superreducido"  # 4 %
    EXENTO = "exento"  # 0 %


TIPO_IVA_PORCENTAJE: dict[TipoIVA, int] = {
    TipoIVA.GENERAL: 21,
    TipoIVA.REDUCIDO: 10,
    TipoIVA.SUPERREDUCIDO: 4,
    TipoIVA.EXENTO: 0,
}


def enum_column(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    """Columna VARCHAR + CHECK que guarda el *valor* del enum, no su nombre."""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
    )
