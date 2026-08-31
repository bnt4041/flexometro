"""Qué cosas de la aplicación merecen que alguien se entere.

Vive en `core` y no dentro de notificaciones porque tiene DOS consumidores:
los avisos a personas (campana, correo, WhatsApp) y los webhooks a sistemas
de fuera. Son el mismo hecho contado a dos públicos, y con dos catálogos
paralelos uno acabaría teniendo eventos que el otro no.

Un catálogo y no un enum cerrado porque cada módulo declara lo suyo: `obras`
sabe qué es una obra estancada y `prl` qué es un documento a punto de
caducar, y ninguno de los dos tiene por qué aparecer en un fichero central
que haya que tocar cada vez.

Dos formas de enterarse de que hay que avisar, y son distintas de verdad:

- `HECHO`: ha pasado algo. Lo emite el código en el momento (se ha firmado un
  documento, ha entrado una oferta). Barato y exacto.
- `VIGILANCIA`: no ha pasado nada, y ESE es el problema — una obra que lleva
  tres meses sin moverse, un documento que caduca la semana que viene. No hay
  ningún momento en que «ocurra», así que hay que ir a buscarlo cada cierto
  tiempo (ver `vigilancia.py`).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Disparador(StrEnum):
    HECHO = "hecho"
    VIGILANCIA = "vigilancia"


@dataclass(frozen=True)
class Parametro:
    """Un hueco que rellena quien configura la regla: «avisar cuando lleve
    ___ días». Sin esto habría que crear un tipo de evento por cada número."""

    nombre: str
    etiqueta: str
    por_defecto: int
    minimo: int = 1
    maximo: int = 3650
    sufijo: str = "días"


@dataclass(frozen=True)
class TipoEvento:
    codigo: str
    #: A qué módulo pertenece. Manda para dos cosas: no ofrecer eventos de
    #: módulos apagados, y no avisar a quien no tiene permiso de verlos.
    modulo: str
    etiqueta: str
    descripcion: str
    disparador: Disparador
    parametros: tuple[Parametro, ...] = ()


_CATALOGO: dict[str, TipoEvento] = {}
#: Cómo se buscan los candidatos de una vigilancia. Va aparte del catálogo
#: para que este siga siendo datos puros y se pueda serializar al frontend.
_BUSCADORES: dict[str, Callable] = {}


def registrar(evento: TipoEvento, buscador: Callable | None = None) -> TipoEvento:
    """Da de alta un tipo de evento. Se llama al importar cada módulo.

    Un código repetido revienta: dos módulos peleándose por el mismo nombre
    haría que las reglas de uno dispararan avisos del otro."""
    if evento.codigo in _CATALOGO:
        raise ValueError(f"El evento «{evento.codigo}» ya está registrado")
    if evento.disparador is Disparador.VIGILANCIA and buscador is None:
        raise ValueError(
            f"«{evento.codigo}» es una vigilancia y necesita quien busque sus candidatos"
        )
    _CATALOGO[evento.codigo] = evento
    if buscador is not None:
        _BUSCADORES[evento.codigo] = buscador
    return evento


def catalogo() -> list[TipoEvento]:
    return sorted(_CATALOGO.values(), key=lambda e: (e.modulo, e.etiqueta))


def obtener(codigo: str) -> TipoEvento | None:
    return _CATALOGO.get(codigo)


def buscador_de(codigo: str) -> Callable | None:
    return _BUSCADORES.get(codigo)
