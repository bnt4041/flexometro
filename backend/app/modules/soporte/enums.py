from enum import StrEnum


class TipoTicket(StrEnum):
    INCIDENCIA = "incidencia"
    PETICION = "peticion"
    DUDA = "duda"


class EstadoTicket(StrEnum):
    """`ESPERANDO` es la pelota en el tejado de quien lo abrió.

    Sin ese estado, un ticket parado por falta de respuesta parece parado por
    culpa de quien lo atiende, y las métricas de tiempo de resolución mienten.
    """

    NUEVO = "nuevo"
    ABIERTO = "abierto"
    ESPERANDO = "esperando"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"


class Prioridad(StrEnum):
    BAJA = "baja"
    NORMAL = "normal"
    ALTA = "alta"
    URGENTE = "urgente"


class OrigenFragmento(StrEnum):
    """De dónde salió un trozo indexado."""

    WIKI = "wiki"
    TICKET = "ticket"
