"""El registro de herramientas del copiloto.

Cada herramienta declara a qué módulo pertenece y qué acción hace. Eso no es
documentación: es lo que decide si la herramienta se le ofrece o no al modelo
en cada conversación. Quien no puede ver facturas por pantalla tampoco recibe
la herramienta de buscar facturas, así que el modelo no puede pedirla ni
«equivocarse» — la puerta no está cerrada, es que no existe.

Y las herramientas que escriben no escriben. Devuelven una propuesta que
vuelve al navegador para que la persona la confirme; solo entonces se ejecuta,
por un endpoint aparte que vuelve a comprobar el permiso. Un modelo que se
confunde de cliente o de importe produce una pregunta, no un asiento.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.enums import Alcance
from app.core.permisos import ACCIONES, PermisoModulo


class HerramientaInvalida(Exception):
    """Lo que ha pedido el modelo no se puede hacer. El texto vuelve al
    modelo como resultado de la herramienta para que rectifique, no al
    usuario como error: que el modelo se equivoque al llamar a algo es
    normal y tiene arreglo dentro de la misma conversación."""


@dataclass
class Contexto:
    """Lo que toda herramienta necesita saber. Se construye una vez por turno.

    `permisos` viene resuelto de antemano para no repetir la consulta por cada
    llamada, y `alcance_de` es lo que una herramienta de lectura debe usar
    para decidir si filtra por autor.
    """

    session: AsyncSession
    principal: Principal
    permisos: dict[str, PermisoModulo]
    modulos_activos: frozenset[str]
    #: En qué pantalla está la persona ahora mismo. Lo manda el widget.
    ruta_actual: str | None = None

    def alcance_de(self, modulo: str, accion: str) -> Alcance:
        permiso = self.permisos.get(modulo)
        return permiso.de(accion) if permiso else Alcance.NINGUNO

    def puede(self, modulo: str | None, accion: str | None) -> bool:
        if modulo is None or accion is None:
            return True
        if modulo not in self.modulos_activos:
            return False
        return self.alcance_de(modulo, accion) != Alcance.NINGUNO


@dataclass(frozen=True)
class Propuesta:
    """Una escritura pendiente de que alguien diga que sí.

    `datos` viaja al navegador y vuelve tal cual en la confirmación. No se
    guarda en base: mientras nadie confirme, esto no ha pasado. Al volver se
    revalida entero contra el servicio dueño, así que no importa que haya
    estado en manos del cliente.
    """

    #: Clave del ejecutor que la aplicará (ver `ejecutores.py`).
    accion: str
    #: Qué se le enseña a la persona antes de confirmar. En una línea.
    resumen: str
    datos: dict[str, Any]
    #: Detalle campo a campo para que se pueda revisar sin adivinar.
    campos: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    #: JSON Schema de los argumentos, construido a partir del contexto. Es una
    #: función y no un dict fijo porque el esquema depende de los permisos: a
    #: quien no ve facturas no se le enumera «factura» entre los tipos que
    #: puede pedir, así que el modelo no llega ni a intentarlo.
    parametros: Callable[["Contexto"], dict[str, Any]]
    #: `None` en las que no dependen de ningún módulo (la ayuda, la guía de la
    #: interfaz): negárselas a quien tiene pocos permisos sería justo al revés
    #: de lo que hace falta.
    modulo: str | None
    accion: str | None
    ejecutar: Callable[["Contexto", dict[str, Any]], Awaitable[Any]]
    #: Si es `True`, `ejecutar` devuelve una `Propuesta` y NO escribe nada.
    escribe: bool = False
    #: Para las que dependen de varios módulos a la vez: se descartan si no
    #: queda nada que puedan hacer.
    disponible_si: Callable[["Contexto"], bool] | None = None


_HERRAMIENTAS: dict[str, Herramienta] = {}


def registrar(herramienta: Herramienta) -> Herramienta:
    if herramienta.nombre in _HERRAMIENTAS:
        raise ValueError(f"La herramienta «{herramienta.nombre}» ya está registrada")
    if herramienta.accion is not None and herramienta.accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {herramienta.accion!r} (son {ACCIONES})")
    _HERRAMIENTAS[herramienta.nombre] = herramienta
    return herramienta


def obtener(nombre: str) -> Herramienta | None:
    return _HERRAMIENTAS.get(nombre)


def todas() -> list[Herramienta]:
    return sorted(_HERRAMIENTAS.values(), key=lambda h: h.nombre)


def disponibles(contexto: Contexto, *, permitir_escritura: bool = True) -> list[Herramienta]:
    """Las que esta persona puede usar de verdad, aquí y ahora."""
    return [
        h
        for h in todas()
        if contexto.puede(h.modulo, h.accion)
        and (permitir_escritura or not h.escribe)
        and (h.disponible_si is None or h.disponible_si(contexto))
    ]


def formato_openai(
    herramientas: list[Herramienta], contexto: Contexto
) -> list[dict[str, Any]]:
    """Al formato que espera el function-calling del modelo."""
    return [
        {
            "type": "function",
            "function": {
                "name": h.nombre,
                "description": h.descripcion,
                "parameters": h.parametros(contexto),
            },
        }
        for h in herramientas
    ]


def _modulos_a_resolver() -> set[str]:
    from app.modules.ia.copiloto import objetos
    from app.modules.importador import destinos
    from app.modules.informes import fuentes

    modulos = {h.modulo for h in todas() if h.modulo}
    modulos |= {t.modulo for t in objetos.catalogo()}
    modulos |= {f.modulo for f in fuentes.catalogo()}
    modulos |= {d.modulo for d in destinos.catalogo()}
    return modulos


async def contexto_de(session: AsyncSession, principal: Principal) -> Contexto:
    """Resuelve permisos y módulos activos una sola vez por turno."""
    from app.core.permisos import permiso_efectivo
    from app.modules.core.service import active_module_codes

    activos = frozenset(await active_module_codes(session, principal.organization_id))
    # Los módulos a resolver no salen solo de `Herramienta.modulo`: casi todas
    # las herramientas valen para varios (buscar_objetos sirve obras, terceros,
    # facturas…) y declaran `modulo=None` porque el permiso depende de lo que
    # se pida dentro. Hay que mirar, por tanto, lo que esas herramientas
    # pueden llegar a tocar. Resolver de menos aquí no da un error: da un
    # copiloto que cree no tener permiso para nada.
    permisos = {
        m: await permiso_efectivo(session, principal, m)
        for m in sorted(_modulos_a_resolver() & activos)
    }
    return Contexto(
        session=session,
        principal=principal,
        permisos=permisos,
        modulos_activos=activos,
    )
