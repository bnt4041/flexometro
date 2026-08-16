"""Bus de eventos en proceso.

Existe para respetar la dirección de las dependencias entre módulos. Cambiar
una tarifa de proveedor tiene que propagarse al precio básico que la usa, pero
`catalogo` no puede importar `presupuestos`: la dependencia va justo al revés.

Con el bus, `catalogo` emite un hecho ("esta tarifa ha cambiado") sin saber
quién escucha, y `presupuestos` se suscribe cuando se registra. Si el módulo
suscriptor no está instalado, el evento simplemente no tiene oyentes.

No es una cola: los manejadores corren en la misma transacción que el emisor,
que es justo lo que se quiere para un recálculo en cascada — o cuadra todo, o
no se guarda nada.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        if handler in self._handlers[event]:
            return  # registrar dos veces el mismo módulo no duplica el efecto
        self._handlers[event].append(handler)

    async def emit(self, event: str, **payload: Any) -> None:
        for handler in self._handlers[event]:
            logger.debug("evento %s -> %s", event, handler.__qualname__)
            await handler(**payload)

    def listeners(self, event: str) -> list[Handler]:
        return list(self._handlers[event])


bus = EventBus()


# --- Nombres de evento ---

# Una tarifa de proveedor se ha creado, modificado o borrado.
# payload: session, producto_id
PRECIO_SUMINISTRO_CAMBIADO = "catalogo.precio_suministro.cambiado"
