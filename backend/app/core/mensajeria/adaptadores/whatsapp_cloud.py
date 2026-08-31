"""Adaptador de WhatsApp contra la API oficial (Cloud API de Meta).

Este es el destino: cuando Flexómetro deje de ser una demo, el WhatsApp tiene
que salir de aquí y no del puente de WhatsApp Web, porque una cuenta personal
mandando automatismos acaba cerrada.

⚠️ SIN VERIFICAR CONTRA META. Está escrito con la forma que documenta la Cloud
API, pero no se ha ejecutado nunca contra la API real porque hoy no hay número
de empresa ni token. Antes de ponerlo en producción hay que probarlo de
verdad; lo que sí está resuelto es que enchufarlo no obliga a tocar el
circuito de firma.

Lo que hay que tener hecho ANTES de que esto sirva, y no depende del código:

1. Un número dado de alta en WhatsApp Business Platform, con su
   `phone_number_id` y un token permanente.
2. Las plantillas APROBADAS por Meta. Fuera de la ventana de 24 h desde que
   el usuario escribe —que es siempre nuestro caso, porque la conversación la
   iniciamos nosotros— no se puede mandar texto libre. Hacen falta dos:
   - una de categoría «utilidad» para los avisos, con un hueco `{{1}}`;
   - otra de categoría «autenticación» para el código de verificación, que
     tiene reglas propias (el código va en un botón de copiar, no en el
     cuerpo).
   Los nombres de ambas se configuran en Ajustes; el código no los inventa.
"""

from typing import TYPE_CHECKING

import httpx

from app.core.mensajeria.puerto import (
    Canal,
    Destinatario,
    Mensaje,
    MensajeriaError,
    TipoMensaje,
    normalizar_telefono,
    ofuscar_telefono,
)

if TYPE_CHECKING:
    from app.modules.core.settings_models import ConfiguracionWhatsApp

_TIEMPO_ESPERA = 30.0


class AdaptadorWhatsAppCloud:
    def __init__(self, config: "ConfiguracionWhatsApp") -> None:
        self._config = config

    @property
    def canal(self) -> Canal:
        return Canal.WHATSAPP

    def direccion_de(self, destinatario: Destinatario) -> str | None:
        if not destinatario.telefono:
            return None
        try:
            return normalizar_telefono(destinatario.telefono, self._config.prefijo_pais)
        except MensajeriaError:
            return None

    def ofuscar(self, destinatario: Destinatario) -> str:
        return ofuscar_telefono(destinatario.telefono)

    async def enviar(self, destinatario: Destinatario, mensaje: Mensaje) -> None:
        numero = self.direccion_de(destinatario)
        if not numero:
            raise MensajeriaError(f"{destinatario.nombre} no tiene un teléfono utilizable")

        config = self._config
        if not config.cloud_phone_number_id or not config.cloud_token:
            raise MensajeriaError(
                "Falta el número de empresa o el token de la API de WhatsApp "
                "(Administración → Ajustes globales → WhatsApp)"
            )

        plantilla = (
            config.plantilla_codigo
            if mensaje.tipo == TipoMensaje.CODIGO_VERIFICACION
            else config.plantilla_aviso
        )
        if not plantilla:
            raise MensajeriaError(
                f"No hay plantilla configurada para mensajes de tipo «{mensaje.tipo.value}»"
            )

        cuerpo = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero,
            "type": "template",
            "template": {
                "name": plantilla,
                "language": {"code": config.idioma_plantilla},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": v}
                            # Sin variables se manda el texto entero como
                            # único hueco: sirve para una plantilla simple de
                            # un solo `{{1}}`.
                            for v in (mensaje.variables or (mensaje.texto,))
                        ],
                    }
                ],
            },
        }

        async with httpx.AsyncClient(timeout=_TIEMPO_ESPERA) as cliente:
            try:
                respuesta = await cliente.post(
                    f"https://graph.facebook.com/{config.cloud_version}"
                    f"/{config.cloud_phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {config.cloud_token}"},
                    json=cuerpo,
                )
            except httpx.HTTPError as exc:
                raise MensajeriaError(f"No se ha podido contactar con WhatsApp: {exc}") from exc

        if respuesta.status_code >= 400:
            # Meta devuelve el motivo en `error.message`, que es lo único
            # accionable (plantilla no aprobada, token caducado, número no
            # registrado). El JSON entero no aporta.
            detalle = respuesta.text[:300]
            try:
                detalle = respuesta.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise MensajeriaError(f"WhatsApp rechazó el mensaje: {detalle}")

        if mensaje.adjuntos:
            # Mandar un documento exige subirlo antes a /media y luego
            # referenciar su id. No está hecho porque hoy no hay forma de
            # probarlo; se avisa en vez de fallar en silencio y dejar a
            # alguien esperando un PDF que no va a llegar.
            raise MensajeriaError(
                "El envío de adjuntos por la API oficial todavía no está implementado"
            )
