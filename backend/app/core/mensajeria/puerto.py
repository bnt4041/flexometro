"""El puerto de mensajería: lo que el dominio sabe de «mandarle algo a
alguien», y nada más.

Aquí NO aparece SMTP, ni GOWA, ni la API de Meta. Quien pide una firma dice
«manda este mensaje a esta persona por este canal» y se acabó; qué hay al
otro lado lo decide `fabrica.py`, que es el único sitio que conoce a los
adaptadores concretos.

Esto existe porque el proveedor de WhatsApp va a cambiar. Hoy la plataforma
habla con un puente de WhatsApp Web (GOWA), que vale para enseñar el producto
pero no se sostiene en producción: la cuenta que hay detrás es una cuenta
personal y mandar automatismos por ahí acaba en cierre. El día que esto sea
una empresa de verdad habrá que pasar a la API oficial de WhatsApp Business,
y ese cambio tiene que ser un adaptador nuevo y un ajuste en la
configuración — no tocar el circuito de firma.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Canal(StrEnum):
    """Por dónde sale un mensaje.

    Es el canal, no el proveedor: `WHATSAPP` vale igual para el puente de
    WhatsApp Web de hoy que para la API oficial de mañana. El dominio razona
    sobre canales (para no mandar el enlace y su código por el mismo sitio);
    el proveedor concreto le da igual.
    """

    EMAIL = "email"
    WHATSAPP = "whatsapp"


class PreferenciaCanal(StrEnum):
    """Por dónde se quiere que salga algo, dicho por quien lo manda.

    `AUTO` deja decidir al dominio según lo que sepa de cada persona (si hay
    teléfono, si el canal está en marcha). Los demás valores son una orden:
    si alguien pide WhatsApp y esa persona no tiene móvil, no se manda por
    correo a escondidas — se dice que no se ha podido.

    `AMBOS` manda por los dos. Tiene sentido para el enlace («que le llegue
    sí o sí»), y ojo con usarlo para el código de verificación: si el enlace
    y su código viajan por los dos mismos canales, ya no hay dos factores.
    """

    AUTO = "auto"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    AMBOS = "ambos"

    def canales(self) -> tuple["Canal", ...]:
        """Los canales concretos que pide, o vacío si lo deja en `AUTO`."""
        if self is PreferenciaCanal.EMAIL:
            return (Canal.EMAIL,)
        if self is PreferenciaCanal.WHATSAPP:
            return (Canal.WHATSAPP,)
        if self is PreferenciaCanal.AMBOS:
            return (Canal.WHATSAPP, Canal.EMAIL)
        return ()


class TipoMensaje(StrEnum):
    """Para qué es el mensaje, dicho en lenguaje del dominio.

    Existe por una restricción muy real de la API oficial de WhatsApp: fuera
    de la ventana de 24 h no se puede mandar texto libre, solo plantillas
    aprobadas, y un código de verificación tiene que ir en una plantilla de
    categoría «autenticación», distinta de la de un aviso normal.

    En vez de que el dominio hable de plantillas —que es vocabulario de Meta y
    no significa nada para el correo ni para el puente de WhatsApp Web— dice
    QUÉ está mandando, y cada adaptador traduce. Los canales que no
    distinguen, simplemente lo ignoran.
    """

    AVISO = "aviso"
    CODIGO_VERIFICACION = "codigo_verificacion"


class MensajeriaError(Exception):
    """Un envío que no ha salido. Los adaptadores traducen a esto los fallos
    de su tecnología (SMTP, HTTP, la respuesta rara de un puente) para que
    quien llama no tenga que conocerlas."""


@dataclass(frozen=True)
class Destinatario:
    """A quién se le manda, con TODAS las direcciones que se le conocen.

    Se pasa entero a cualquier adaptador y cada uno coge la que sabe usar:
    el de correo el `email`, los de WhatsApp el `telefono`. Así el dominio no
    tiene que preguntarse qué dirección hace falta para cada canal.
    """

    nombre: str
    email: str | None = None
    telefono: str | None = None


@dataclass(frozen=True)
class Adjunto:
    nombre_archivo: str
    contenido: bytes
    content_type: str = "application/pdf"


@dataclass(frozen=True)
class Mensaje:
    """El mismo mensaje en las dos formas que necesitan los canales.

    El correo quiere asunto y HTML; WhatsApp quiere texto plano y no tiene
    asunto. En vez de que el dominio escriba una versión por canal —y que se
    desincronicen a la primera— escribe las dos aquí, y cada adaptador usa la
    que le sirve. `html` es opcional: sin él, el de correo maqueta el texto.
    """

    asunto: str
    texto: str
    html: str | None = None
    adjuntos: tuple[Adjunto, ...] = field(default_factory=tuple)
    tipo: TipoMensaje = TipoMensaje.AVISO
    #: Los huecos de la plantilla, en orden, para los canales que trabajan
    #: con plantillas aprobadas. Quien no las use manda `texto` y ya está,
    #: pero el dominio los rellena SIEMPRE: si solo mandara el texto ya
    #: montado, el día que se pase a la API oficial no habría de dónde
    #: sacarlos y habría que reescribir cada mensaje.
    variables: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class ProveedorMensajeria(Protocol):
    """Lo que tiene que saber hacer cualquier canal para que el dominio lo
    pueda usar. Un adaptador NO hereda de esto: basta con tener esta forma."""

    @property
    def canal(self) -> Canal:
        """Por cuál de los canales del dominio responde este proveedor."""
        ...

    def direccion_de(self, destinatario: Destinatario) -> str | None:
        """La dirección que este canal usaría, o None si no puede alcanzar a
        esta persona (un correo para SMTP, un teléfono para WhatsApp).

        Sirve para dos cosas a la vez: decidir si el canal es viable y saber
        adónde iría, sin llegar a intentar el envío."""
        ...

    def ofuscar(self, destinatario: Destinatario) -> str:
        """La dirección tapada, para poder decir «te lo hemos mandado a…»
        sin enseñarla entera a quien tenga el enlace en la mano. Cada canal
        sabe tapar la suya: no es lo mismo un correo que un teléfono."""
        ...

    async def enviar(self, destinatario: Destinatario, mensaje: Mensaje) -> None:
        """Manda el mensaje. Lanza `MensajeriaError` si no sale."""
        ...


# ── Capacidad opcional: vincular por QR ─────────────────────────────────


@dataclass(frozen=True)
class Vinculacion:
    """Si el proveedor tiene una cuenta lista para mandar, y cuál."""

    vinculado: bool
    #: El número o el nombre de la cuenta vinculada, para que quien lo mire
    #: sepa CUÁL es — no vaya a estar mandando desde el móvil que no toca.
    descripcion: str | None = None
    device_id: str | None = None


@dataclass(frozen=True)
class CodigoQr:
    #: El PNG en crudo. Se devuelve la imagen y no su URL a propósito: la que
    #: da el proveedor apunta a su propio host, que no tiene por qué ser
    #: alcanzable desde el navegador de quien está configurando.
    imagen_png: bytes
    #: Lo que dura antes de caducar. WhatsApp los rota rápido.
    segundos: int


@runtime_checkable
class VinculacionPorQr(Protocol):
    """Capacidad OPCIONAL: vincular una cuenta escaneando un código QR.

    Va aparte de `ProveedorMensajeria` porque no todos los proveedores
    vinculan igual, ni vinculan siquiera. Los que se conectan como WhatsApp
    Web sí: hay un móvil que escanea. La API oficial no — allí se da de alta
    un número en Meta y se configura con credenciales, sin QR ninguno.

    Que sea una capacidad y no un método más del puerto es lo que permite a
    la pantalla de ajustes preguntar «¿esto se vincula escaneando?» en vez de
    saber qué proveedor hay puesto. Al pasar a la API oficial, la sección del
    QR desaparece sola.
    """

    async def estado_vinculacion(self) -> Vinculacion:
        """Si hay cuenta lista para mandar. No lanza si no la hay: devuelve
        `vinculado=False`, que es una respuesta, no un error."""
        ...

    async def iniciar_vinculacion(self) -> CodigoQr:
        """Arranca el emparejamiento y devuelve el QR a escanear."""
        ...

    async def desvincular(self) -> None:
        """Cierra la sesión de la cuenta vinculada."""
        ...


# ── Utilidades de dirección, compartidas por los adaptadores ─────────────
# Normalizar un teléfono no es cosa de GOWA ni de Meta: las dos APIs quieren
# lo mismo (E.164 sin '+'), así que vive en el puerto y no se duplica.


def normalizar_telefono(bruto: str | None, prefijo_por_defecto: str = "34") -> str:
    """Pasa un teléfono como lo escribe una persona a E.164 sin '+'.

    `+34 600 11 22 33`, `0034 600112233` y `600112233` acaban los tres en
    `34600112233`.
    """
    limpio = re.sub(r"[^\d+]", "", bruto or "")
    if not limpio:
        raise MensajeriaError("El teléfono está vacío")

    if limpio.startswith("+"):
        limpio = limpio[1:]
    elif limpio.startswith("00"):
        # Prefijo internacional a la europea: 00 34 600…
        limpio = limpio[2:]
    elif len(limpio) <= 9:
        # Número nacional escrito sin prefijo. El corte está en 9 dígitos
        # porque es donde ya no cabe un prefijo de país delante: con más
        # dígitos se asume que quien lo escribió ya lo puso.
        limpio = f"{prefijo_por_defecto}{limpio}"

    if not limpio.isdigit() or len(limpio) < 8:
        raise MensajeriaError(f"El teléfono «{bruto}» no parece un número válido")
    return limpio


def ofuscar_email(email: str | None) -> str:
    """`beni4041@gmail.com` -> `b***@gmail.com`."""
    usuario, _, dominio = (email or "").partition("@")
    return f"{usuario[:1]}***@{dominio}" if dominio else "***"


def ofuscar_telefono(telefono: str | None) -> str:
    """`+34 600 112 233` -> `···233`."""
    digitos = "".join(c for c in telefono or "" if c.isdigit())
    return f"···{digitos[-3:]}" if len(digitos) >= 3 else "···"
