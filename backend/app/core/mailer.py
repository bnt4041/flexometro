"""Envío de correo, con el SMTP de la plataforma (Ajustes → SMTP) o el
propio de una organización (`ConfiguracionSmtpPlataforma`/
`ConfiguracionSmtpOrganizacion` — misma forma, de ahí que esta función no
importe ninguna de las dos en concreto, solo duck-type).

Best-effort y sin cola, igual que el webhook de n8n en facturación: si el
SMTP no está configurado o el envío falla, se informa con una excepción
clara y quien llama decide qué hacer — normalmente, seguir adelante con la
operación que lo disparó (crear el usuario, por ejemplo) y ofrecer un
"reintentar envío"/"enviar correo de prueba" aparte, no bloquearla.

⚠️ El tipo de `config` se importa solo bajo `TYPE_CHECKING`, nunca en
tiempo de ejecución: `app.modules.core.settings_models` vive dentro del
paquete `app.modules.core`, y `billing_router.py`/`settings_router.py`
(también dentro de ese paquete) importan este módulo a nivel de fichero —
si aquí se importara el modelo en tiempo de ejecución, quien importe
`app.core.mailer` ANTES que `app.modules.core` (cualquier script suelto,
no solo `app.main`) dispararía un ciclo real: mailer → settings_models →
(re-entra en) `app.modules.core.__init__` → router → billing_router →
mailer, mailer todavía a medias. `app.main` tiene la suerte de importar en
un orden que lo esquiva, pero es frágil apoyarse en eso.
"""

import logging
from email.message import EmailMessage
from typing import TYPE_CHECKING

import aiosmtplib

if TYPE_CHECKING:
    from app.modules.core.settings_models import ConfiguracionSmtpPlataforma

logger = logging.getLogger(__name__)


class MailerError(Exception):
    pass


async def enviar_correo(
    config: "ConfiguracionSmtpPlataforma", *, destinatario: str, asunto: str, cuerpo_html: str
) -> None:
    if not config.host or not config.remitente:
        raise MailerError(
            "El SMTP de la plataforma no está configurado (Administración → Ajustes SMTP)"
        )

    mensaje = EmailMessage()
    mensaje["From"] = config.remitente
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content("Este correo requiere un cliente compatible con HTML.")
    mensaje.add_alternative(cuerpo_html, subtype="html")

    # El puerto 465 es TLS implícito desde el primer byte (SMTPS); el 587 (y
    # el resto) es texto plano que se negocia a TLS con STARTTLS a mitad de
    # conversación — son protocolos de arranque distintos, no una opción
    # "con/sin TLS" homogénea. Mezclarlos da exactamente "Unexpected EOF
    # received": el lado que espera TLS desde ya cierra la conexión al ver
    # texto plano donde esperaba un handshake. `usa_tls=False` (sin cifrar)
    # solo tiene sentido para un relay local de pruebas.
    tls_implicito = config.usa_tls and config.puerto == 465
    try:
        await aiosmtplib.send(
            mensaje,
            hostname=config.host,
            port=config.puerto,
            username=config.usuario or None,
            password=config.password or None,
            start_tls=config.usa_tls and not tls_implicito,
            use_tls=tls_implicito,
        )
    except Exception as exc:  # aiosmtplib lanza varias excepciones propias de SMTP/red
        logger.warning("No se pudo enviar el correo a %s: %s", destinatario, exc)
        raise MailerError(f"No se pudo enviar el correo: {exc}") from exc
