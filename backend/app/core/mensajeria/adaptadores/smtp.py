"""Adaptador de correo. Envuelve `app.core.mailer`, que sigue siendo el que
habla SMTP de verdad.

Se envuelve en vez de moverlo porque el correo de la plataforma (altas de
usuario, avisos de facturación) lo usa directamente y no tiene por qué pasar
por el puerto. Aquí solo se le da la forma que el puerto espera, para que el
circuito de firma pueda tratar correo y WhatsApp exactamente igual.
"""

from typing import TYPE_CHECKING

from app.core.mensajeria.puerto import (
    Canal,
    Destinatario,
    Mensaje,
    MensajeriaError,
    ofuscar_email,
)

if TYPE_CHECKING:
    from app.modules.core.settings_models import ConfiguracionSmtpPlataforma


class AdaptadorSmtp:
    def __init__(self, config: "ConfiguracionSmtpPlataforma") -> None:
        self._config = config

    @property
    def canal(self) -> Canal:
        return Canal.EMAIL

    def direccion_de(self, destinatario: Destinatario) -> str | None:
        return destinatario.email or None

    def ofuscar(self, destinatario: Destinatario) -> str:
        return ofuscar_email(destinatario.email)

    async def enviar(self, destinatario: Destinatario, mensaje: Mensaje) -> None:
        from app.core.mailer import MailerError, enviar_correo

        direccion = self.direccion_de(destinatario)
        if not direccion:
            raise MensajeriaError(f"{destinatario.nombre} no tiene correo")

        # Sin HTML se maqueta el texto plano: un salto de línea no se ve en
        # HTML, y el mensaje llegaría todo pegado en un párrafo.
        cuerpo = mensaje.html or "".join(
            f"<p>{linea}</p>" for linea in (mensaje.texto or "").split("\n\n") if linea.strip()
        )
        try:
            await enviar_correo(
                self._config,
                destinatario=direccion,
                asunto=mensaje.asunto,
                cuerpo_html=cuerpo,
                adjuntos=[
                    (a.nombre_archivo, a.content_type, a.contenido) for a in mensaje.adjuntos
                ]
                or None,
            )
        except MailerError as exc:
            raise MensajeriaError(str(exc)) from exc
