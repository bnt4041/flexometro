from enum import StrEnum


class EstadoEjecucion(StrEnum):
    """Cómo acabó una pasada del flujo.

    `PARCIAL` existe porque un flujo puede hacer tres cosas bien y fallar en
    la cuarta. Marcarlo como fallido entero escondería que lo anterior sí
    pasó —y en un flujo que manda correos, eso importa mucho.
    """

    EN_CURSO = "en_curso"
    COMPLETADA = "completada"
    FALLIDA = "fallida"
    PARCIAL = "parcial"


class EstadoPaso(StrEnum):
    OK = "ok"
    ERROR = "error"
    #: No se ejecutó porque la rama no pasaba por él. No es un fallo: es la
    #: mitad del árbol que no tocaba.
    OMITIDO = "omitido"
