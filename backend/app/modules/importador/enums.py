from enum import StrEnum


class EstadoImportacion(StrEnum):
    """En qué punto está.

    `PARCIAL` es el caso normal de una hoja real: casi nunca entran las 300
    filas. Distinguirlo de `FALLIDA` es lo que permite decir «entraron 287,
    mira estas 13» en vez de «no ha funcionado».
    """

    #: Subida y leída; falta mapear y ejecutar.
    PREPARADA = "preparada"
    COMPLETADA = "completada"
    PARCIAL = "parcial"
    FALLIDA = "fallida"
