from enum import StrEnum


class EstadoEntrega(StrEnum):
    """En qué punto está un aviso a un sistema de fuera.

    `AGOTADA` no es lo mismo que `FALLIDA`: agotada significa que ya no se va
    a reintentar más. Distinguirlas es lo que permite tener una pantalla de
    «esto se ha perdido, míralo» que no esté llena de cosas que aún van a
    salir solas.
    """

    PENDIENTE = "pendiente"
    ENTREGADA = "entregada"
    #: Falló, pero le quedan intentos.
    FALLIDA = "fallida"
    #: Se acabaron los intentos. Requiere que alguien mire.
    AGOTADA = "agotada"
