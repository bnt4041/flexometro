"""Qué tipos de nodo existen y qué hace cada uno.

Un nodo tiene la misma forma siempre: recibe lo que han producido los nodos
anteriores, lee sus parámetros (que pueden ser expresiones sobre esos datos),
hace lo suyo y devuelve dos cosas — los datos que produce y POR QUÉ SALIDA
sale. Lo segundo es lo que permite ramas: un nodo de condición tiene dos
salidas y solo se sigue una.

Los tipos se registran en una tabla, no se enchufan con `if`: añadir uno
nuevo es escribir su ejecutor y registrarlo, sin tocar el motor.
"""

import ipaddress
import logging
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SALIDA_PRINCIPAL = "principal"


@dataclass(frozen=True)
class CampoNodo:
    """Un hueco que rellena quien monta el flujo."""

    nombre: str
    etiqueta: str
    #: `texto` | `texto_largo` | `numero` | `seleccion` | `booleano`
    tipo: str = "texto"
    opciones: tuple[tuple[str, str], ...] = ()
    ayuda: str = ""
    obligatorio: bool = True
    por_defecto: Any = None
    #: Si admite `{{ ... }}`. Se marca para poder avisarlo en el editor.
    admite_expresiones: bool = True


@dataclass(frozen=True)
class TipoNodo:
    tipo: str
    #: `disparador` arranca el flujo; `accion` va después. Un flujo tiene
    #: exactamente un disparador — con dos, no habría un punto de partida.
    categoria: str
    etiqueta: str
    descripcion: str
    icono: str = "square"
    campos: tuple[CampoNodo, ...] = ()
    #: `(clave, etiqueta)`. Con más de una hay ramas.
    salidas: tuple[tuple[str, str], ...] = ((SALIDA_PRINCIPAL, "Salida"),)


#: `(session, organization_id, parametros_ya_resueltos) -> (datos, ruta)`
Ejecutor = Callable[[AsyncSession, uuid.UUID, dict], Awaitable[tuple[dict, str]]]

_TIPOS: dict[str, TipoNodo] = {}
_EJECUTORES: dict[str, Ejecutor] = {}


def registrar(tipo: TipoNodo, ejecutor: Ejecutor | None = None) -> TipoNodo:
    if tipo.tipo in _TIPOS:
        raise ValueError(f"El nodo «{tipo.tipo}» ya está registrado")
    _TIPOS[tipo.tipo] = tipo
    if ejecutor is not None:
        _EJECUTORES[tipo.tipo] = ejecutor
    return tipo


def catalogo() -> list[TipoNodo]:
    return sorted(_TIPOS.values(), key=lambda t: (t.categoria != "disparador", t.etiqueta))


def obtener(tipo: str) -> TipoNodo | None:
    return _TIPOS.get(tipo)


def ejecutor_de(tipo: str) -> Ejecutor | None:
    return _EJECUTORES.get(tipo)


class NodoError(Exception):
    pass


# ── Acciones ────────────────────────────────────────────────────────────


_OPERADORES = {
    "igual": lambda a, b: str(a) == str(b),
    "distinto": lambda a, b: str(a) != str(b),
    "contiene": lambda a, b: str(b).lower() in str(a or "").lower(),
    "vacio": lambda a, _: a in (None, "", [], {}),
    "no_vacio": lambda a, _: a not in (None, "", [], {}),
    "mayor": lambda a, b: _numero(a) > _numero(b),
    "menor": lambda a, b: _numero(a) < _numero(b),
}


def _numero(valor: Any) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        # Comparar «hola» con 5 no es un error del flujo, es una condición
        # que no se cumple. Reventar aquí pararía todo por un dato vacío.
        return float("-inf")


async def _condicion(session: AsyncSession, organization_id: uuid.UUID, p: dict):
    operador = _OPERADORES.get(p.get("operador", "igual"))
    if operador is None:
        raise NodoError(f"Operador desconocido: {p.get('operador')}")
    cumple = bool(operador(p.get("valor"), p.get("comparar_con")))
    return {"cumple": cumple, "valor": p.get("valor")}, "si" if cumple else "no"


async def _notificar(session: AsyncSession, organization_id: uuid.UUID, p: dict):
    """Manda un aviso por los canales del puerto de mensajería.

    No pasa por las suscripciones: aquí el flujo dice a quién y por dónde, y
    esa es toda la gracia de automatizarlo."""
    from sqlalchemy import select

    from app.core.mensajeria import Canal, Mensaje, MensajeriaError, proveedor_de
    from app.modules.core import notificaciones_service
    from app.modules.core.permisos_models import GrupoUsuario

    titulo = str(p.get("titulo") or "Aviso")
    cuerpo = str(p.get("cuerpo") or "")
    canales = [c.strip() for c in str(p.get("canales") or "campana").split(",") if c.strip()]

    subjects: list[str] = []
    if p.get("grupo_id"):
        subjects = list(
            await session.scalars(
                select(GrupoUsuario.usuario_subject).where(
                    GrupoUsuario.organization_id == organization_id,
                    GrupoUsuario.grupo_id == p["grupo_id"],
                )
            )
        )
    elif p.get("usuario_subject"):
        subjects = [str(p["usuario_subject"])]

    if not subjects:
        raise NodoError("El nodo no tiene a quién avisar")

    enviados = 0
    for subject in subjects:
        if "campana" in canales:
            await notificaciones_service.crear(
                session,
                organization_id=organization_id,
                tipo="automatizacion",
                titulo=titulo,
                cuerpo=cuerpo,
                destinatario_subject=subject,
            )
            enviados += 1
        for nombre in (c for c in canales if c != "campana"):
            proveedor = await proveedor_de(session, organization_id, Canal(nombre))
            if proveedor is None:
                continue
            # Las direcciones se resuelven igual que en los avisos normales.
            from app.modules.notificaciones.service import _direcciones

            destino = await _direcciones(session, organization_id, subject)
            if destino is None or proveedor.direccion_de(destino) is None:
                continue
            try:
                await proveedor.enviar(destino, Mensaje(asunto=titulo, texto=cuerpo))
                enviados += 1
            except MensajeriaError as exc:
                logger.warning("Automatización: no se pudo avisar a %s: %s", subject, exc)

    return {"avisados": len(subjects), "envios": enviados}, SALIDA_PRINCIPAL


#: Redes que un flujo NO puede alcanzar. Sin esto, cualquier usuario podría
#: usar un nodo HTTP para llamar a la base de datos, a MinIO, a Keycloak o a
#: los metadatos del proveedor de nube — todo eso vive en direcciones
#: privadas alcanzables desde este contenedor. Es el agujero clásico (SSRF) y
#: la única defensa que funciona es resolver el nombre y mirar a dónde apunta.
def _destino_permitido(url: str) -> None:
    from urllib.parse import urlparse

    partes = urlparse(url)
    if partes.scheme not in ("http", "https"):
        raise NodoError("La URL tiene que ser http o https")
    if not partes.hostname:
        raise NodoError("La URL no tiene servidor")
    try:
        _, _, direcciones = socket.gethostbyname_ex(partes.hostname)
    except OSError as exc:
        raise NodoError(f"No se ha podido resolver «{partes.hostname}»") from exc

    for texto in direcciones:
        ip = ipaddress.ip_address(texto)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise NodoError(
                f"«{partes.hostname}» apunta a una dirección interna ({texto}); "
                "un flujo no puede llamar a la red privada"
            )


async def _http(session: AsyncSession, organization_id: uuid.UUID, p: dict):
    url = str(p.get("url") or "")
    _destino_permitido(url)
    metodo = str(p.get("metodo") or "POST").upper()

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as cliente:
        try:
            respuesta = await cliente.request(
                metodo,
                url,
                json=p.get("cuerpo") if metodo != "GET" else None,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise NodoError(f"No se ha podido llamar a {url}: {exc}") from exc

    try:
        datos = respuesta.json()
    except ValueError:
        datos = {"texto": respuesta.text[:2000]}
    return (
        {"codigo": respuesta.status_code, "datos": datos},
        SALIDA_PRINCIPAL if respuesta.status_code < 400 else "error",
    )


def registrar_catalogo_inicial() -> None:
    """Idempotente: se puede llamar más de una vez sin reventar."""
    if obtener("condicion") is not None:
        return

    # ── Disparadores ────────────────────────────────────────────────────
    registrar(
        TipoNodo(
            tipo="disparador.evento",
            categoria="disparador",
            etiqueta="Cuando pasa algo",
            descripcion=(
                "Arranca con un evento de Flexómetro: una firma completada, "
                "una obra parada, un documento que caduca…"
            ),
            icono="bell",
            campos=(
                CampoNodo(
                    nombre="evento",
                    etiqueta="Evento",
                    tipo="seleccion",
                    ayuda="Los mismos que usan los avisos y los webhooks.",
                    admite_expresiones=False,
                ),
            ),
        )
    )
    registrar(
        TipoNodo(
            tipo="disparador.webhook",
            categoria="disparador",
            etiqueta="Cuando llaman a una URL",
            descripcion=(
                "Arranca cuando otro sistema hace POST a una dirección propia "
                "de este flujo. Lo que mande llega como datos del disparador."
            ),
            icono="code",
            campos=(),
        )
    )
    registrar(
        TipoNodo(
            tipo="disparador.programado",
            categoria="disparador",
            etiqueta="Cada cierto tiempo",
            descripcion="Arranca solo, cada X minutos.",
            icono="clock",
            campos=(
                CampoNodo(
                    nombre="cada_minutos",
                    etiqueta="Cada (minutos)",
                    tipo="numero",
                    por_defecto=60,
                    admite_expresiones=False,
                ),
            ),
        )
    )

    # ── Acciones ────────────────────────────────────────────────────────
    registrar(
        TipoNodo(
            tipo="condicion",
            categoria="accion",
            etiqueta="Si… entonces",
            descripcion="Parte el flujo en dos caminos según se cumpla algo.",
            icono="layers",
            campos=(
                CampoNodo(
                    nombre="valor",
                    etiqueta="Valor",
                    ayuda="Normalmente una expresión: {{ disparador.titulo }}",
                ),
                CampoNodo(
                    nombre="operador",
                    etiqueta="Operador",
                    tipo="seleccion",
                    opciones=(
                        ("igual", "es igual a"),
                        ("distinto", "es distinto de"),
                        ("contiene", "contiene"),
                        ("mayor", "es mayor que"),
                        ("menor", "es menor que"),
                        ("vacio", "está vacío"),
                        ("no_vacio", "tiene valor"),
                    ),
                    por_defecto="igual",
                    admite_expresiones=False,
                ),
                CampoNodo(
                    nombre="comparar_con", etiqueta="Comparar con", obligatorio=False
                ),
            ),
            salidas=(("si", "Sí"), ("no", "No")),
        ),
        _condicion,
    )
    registrar(
        TipoNodo(
            tipo="notificar",
            categoria="accion",
            etiqueta="Avisar a alguien",
            descripcion="Manda un aviso por campana, correo o WhatsApp.",
            icono="bell",
            campos=(
                CampoNodo(
                    nombre="grupo_id",
                    etiqueta="Grupo",
                    tipo="seleccion",
                    ayuda="A todo el grupo. Se mantiene solo al entrar o salir gente.",
                    admite_expresiones=False,
                ),
                CampoNodo(
                    nombre="canales",
                    etiqueta="Canales",
                    por_defecto="campana",
                    ayuda="Separados por comas: campana, email, whatsapp",
                    admite_expresiones=False,
                ),
                CampoNodo(nombre="titulo", etiqueta="Título"),
                CampoNodo(
                    nombre="cuerpo", etiqueta="Mensaje", tipo="texto_largo", obligatorio=False
                ),
            ),
        ),
        _notificar,
    )
    registrar(
        TipoNodo(
            tipo="http",
            categoria="accion",
            etiqueta="Llamar a una URL",
            descripcion=(
                "Hace una petición a un sistema de fuera. Solo direcciones "
                "públicas: la red interna está cerrada."
            ),
            icono="upload",
            campos=(
                CampoNodo(
                    nombre="metodo",
                    etiqueta="Método",
                    tipo="seleccion",
                    opciones=(("POST", "POST"), ("GET", "GET"), ("PUT", "PUT")),
                    por_defecto="POST",
                    admite_expresiones=False,
                ),
                CampoNodo(nombre="url", etiqueta="URL"),
                CampoNodo(
                    nombre="cuerpo", etiqueta="Cuerpo (JSON)", tipo="texto_largo", obligatorio=False
                ),
            ),
            salidas=((SALIDA_PRINCIPAL, "Correcto"), ("error", "Error")),
        ),
        _http,
    )
