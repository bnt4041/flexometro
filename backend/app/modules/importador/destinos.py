"""A dónde se puede importar, y cómo.

Cada destino declara sus campos y una función que crea UNA fila. Esa función
llama al servicio del módulo dueño (`crear_tercero`, `crear_personal`…) y no
escribe en las tablas directamente. Es la decisión que sostiene todo esto: así
el importador hereda gratis la numeración automática, la validación de la
organización, la auditoría y el control de duplicados, y no puede meter por la
puerta de atrás una fila que la aplicación nunca aceptaría por la de delante.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CampoDestino:
    nombre: str
    etiqueta: str
    #: `texto` | `numero` | `booleano`. Decide cómo se convierte lo que venga
    #: de la hoja, que siempre llega como texto.
    tipo: str = "texto"
    obligatorio: bool = False
    ayuda: str = ""


@dataclass(frozen=True)
class Destino:
    codigo: str
    modulo: str
    etiqueta: str
    descripcion: str
    campos: tuple[CampoDestino, ...]


class FilaInvalida(Exception):
    """Esta fila no vale. El resto de la importación sigue."""


#: `(session, datos_de_la_fila) -> descripción de lo creado`
Creador = Callable[[AsyncSession, dict[str, Any]], Awaitable[str]]

_DESTINOS: dict[str, Destino] = {}
_CREADORES: dict[str, Creador] = {}


def registrar(destino: Destino, creador: Creador) -> Destino:
    if destino.codigo in _DESTINOS:
        raise ValueError(f"El destino «{destino.codigo}» ya está registrado")
    _DESTINOS[destino.codigo] = destino
    _CREADORES[destino.codigo] = creador
    return destino


def catalogo() -> list[Destino]:
    return sorted(_DESTINOS.values(), key=lambda d: d.etiqueta)


def obtener(codigo: str) -> Destino | None:
    return _DESTINOS.get(codigo)


def creador_de(codigo: str) -> Creador | None:
    return _CREADORES.get(codigo)


# ── Conversión de lo que trae la hoja ───────────────────────────────────

_VERDADEROS = {"si", "sí", "s", "true", "1", "x", "yes", "y", "verdadero"}
_FALSOS = {"no", "n", "false", "0", "", "falso"}


def convertir(valor: Any, campo: CampoDestino) -> Any:
    """Texto de una celda al tipo del campo.

    Una celda vacía es `None` y no un cero o un `False`: en una hoja, dejar
    algo en blanco significa «no lo sé», no «vale cero». Meter el valor por
    defecto aquí borraría esa diferencia.
    """
    texto = str(valor if valor is not None else "").strip()
    if texto == "":
        if campo.obligatorio:
            raise FilaInvalida(f"Falta «{campo.etiqueta}»")
        return None

    if campo.tipo == "numero":
        # Las hojas españolas escriben 1.234,56. Se quita el separador de
        # miles y se cambia la coma decimal: `float("1.234,56")` reventaría.
        limpio = texto.replace(".", "").replace(",", ".") if "," in texto else texto
        try:
            return float(limpio)
        except ValueError as exc:
            raise FilaInvalida(f"«{campo.etiqueta}»: «{texto}» no es un número") from exc

    if campo.tipo == "booleano":
        bajo = texto.lower()
        if bajo in _VERDADEROS:
            return True
        if bajo in _FALSOS:
            return False
        raise FilaInvalida(f"«{campo.etiqueta}»: «{texto}» no es sí ni no")

    return texto


# ── Los destinos ────────────────────────────────────────────────────────


async def _crear_tercero(session: AsyncSession, datos: dict) -> str:
    from app.modules.terceros.schemas import TerceroCreate
    from app.modules.terceros.service import CodigoDuplicado, crear_tercero

    try:
        entrada = TerceroCreate(**{k: v for k, v in datos.items() if v is not None})
    except Exception as exc:  # noqa: BLE001
        raise FilaInvalida(str(exc)) from exc
    try:
        tercero = await crear_tercero(session, entrada)
    except CodigoDuplicado as exc:
        raise FilaInvalida(str(exc)) from exc
    return f"{tercero.codigo} · {tercero.razon_social}"


async def _crear_contacto(session: AsyncSession, datos: dict) -> str:
    from sqlalchemy import select

    from app.core.tenancy import datos_autoria, require_organization_id
    from app.modules.terceros.models import Contacto, Tercero

    org_id = require_organization_id()
    tercero_id = None
    codigo = datos.pop("tercero_codigo", None)
    if codigo:
        tercero_id = await session.scalar(
            select(Tercero.id).where(
                Tercero.organization_id == org_id, Tercero.codigo == str(codigo)
            )
        )
        if tercero_id is None:
            # Se rechaza la fila en vez de crear el contacto suelto: un
            # contacto que debía colgar de una empresa y aparece huérfano es
            # peor que uno que falta, porque nadie lo va a echar de menos.
            raise FilaInvalida(f"No existe ningún tercero con código «{codigo}»")

    contacto = Contacto(
        organization_id=org_id,
        tercero_id=tercero_id,
        **{k: v for k, v in datos.items() if v is not None},
        **datos_autoria(),
    )
    session.add(contacto)
    await session.flush()
    return f"{contacto.nombre} {contacto.apellidos or ''}".strip()


async def _crear_personal(session: AsyncSession, datos: dict) -> str:
    from app.modules.obras.schemas import PersonalCreate
    from app.modules.obras.service import crear_personal

    try:
        entrada = PersonalCreate(**{k: v for k, v in datos.items() if v is not None})
    except Exception as exc:  # noqa: BLE001
        raise FilaInvalida(str(exc)) from exc
    persona = await crear_personal(session, entrada)
    return f"{persona.codigo} · {persona.nombre}"


def registrar_catalogo_inicial() -> None:
    """Idempotente: se puede llamar más de una vez sin reventar."""
    if obtener("terceros") is not None:
        return

    registrar(
        Destino(
            codigo="terceros",
            modulo="terceros",
            etiqueta="Terceros (clientes y proveedores)",
            descripcion=(
                "Empresas y autónomos. Sin código se asigna el siguiente "
                "correlativo, igual que al darlos de alta a mano."
            ),
            campos=(
                CampoDestino("codigo", "Código", ayuda="En blanco = automático"),
                CampoDestino("razon_social", "Razón social", obligatorio=True),
                CampoDestino("nif", "NIF"),
                CampoDestino("nombre_comercial", "Nombre comercial"),
                CampoDestino("es_cliente", "Es cliente", tipo="booleano"),
                CampoDestino("es_proveedor", "Es proveedor", tipo="booleano"),
                CampoDestino("es_subcontratista", "Es subcontratista", tipo="booleano"),
                CampoDestino("email", "Correo"),
                CampoDestino("telefono", "Teléfono"),
                CampoDestino("direccion", "Dirección"),
                CampoDestino("poblacion", "Población"),
                CampoDestino("codigo_postal", "Código postal"),
                CampoDestino("provincia", "Provincia"),
            ),
        ),
        _crear_tercero,
    )

    registrar(
        Destino(
            codigo="contactos",
            modulo="terceros",
            etiqueta="Contactos",
            descripcion=(
                "Personas. Con «Código del tercero» se cuelgan de esa empresa; "
                "sin él quedan sueltos en la agenda."
            ),
            campos=(
                CampoDestino("nombre", "Nombre", obligatorio=True),
                CampoDestino("apellidos", "Apellidos"),
                CampoDestino("tercero_codigo", "Código del tercero"),
                CampoDestino("cargo", "Cargo"),
                CampoDestino("email", "Correo"),
                CampoDestino("telefono", "Teléfono"),
                CampoDestino("movil", "Móvil"),
            ),
        ),
        _crear_contacto,
    )

    registrar(
        Destino(
            codigo="personal",
            modulo="obras",
            etiqueta="Personal",
            descripcion="Trabajadores propios, con su categoría y coste hora.",
            campos=(
                CampoDestino("codigo", "Código", ayuda="En blanco = automático"),
                CampoDestino("nombre", "Nombre", obligatorio=True),
                CampoDestino("apellidos", "Apellidos"),
                CampoDestino("categoria", "Categoría"),
                CampoDestino("coste_hora", "Coste hora", tipo="numero"),
            ),
        ),
        _crear_personal,
    )
