"""Adaptador de WhatsApp contra GOWA (go-whatsapp-web-multidevice), un puente
que se conecta a WhatsApp como si fuera un WhatsApp Web más.

⚠️ Esto NO es la API oficial. El número que hay detrás es una cuenta normal,
sujeta a las reglas de uso de una cuenta normal: mandar automatismos a gente
que nunca ha escrito es la forma habitual de que WhatsApp lo cierre. Sirve
para enseñar el producto y para mensajes que el destinatario ESPERA (acaba de
pedírsele una firma). Para funcionar como empresa hay que pasar al adaptador
de la API oficial — por eso esto está detrás del puerto y no suelto.

GOWA admite varias cuentas en una instancia desde la v8 (cabecera
`X-Device-Id`), así que dar a cada organización su número es posible sin
tocar nada de esto: bastaría con rellenar `device_id`.
"""

from typing import TYPE_CHECKING

import httpx

from app.core.mensajeria.puerto import (
    Canal,
    CodigoQr,
    Destinatario,
    Mensaje,
    MensajeriaError,
    Vinculacion,
    normalizar_telefono,
    ofuscar_telefono,
)

if TYPE_CHECKING:
    from app.modules.core.settings_models import ConfiguracionWhatsApp

#: GOWA contesta 200 y este `code` cuando el mensaje ha salido de verdad. El
#: código HTTP no basta: los fallos de negocio (número que no está en
#: WhatsApp, sesión desvinculada) también vienen con 200 y otro `code`.
_CODIGO_OK = "SUCCESS"

#: Un envío es una llamada al puente, que a su vez habla con WhatsApp. 30s da
#: margen a una reconexión sin dejar colgada la petición que lo disparó.
_TIEMPO_ESPERA = 30.0


class AdaptadorGowa:
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
            # Un teléfono ilegible no es un error a estas alturas: significa
            # que este canal no sirve para esta persona, y quien pregunta ya
            # trata None como «por aquí no».
            return None

    def ofuscar(self, destinatario: Destinatario) -> str:
        return ofuscar_telefono(destinatario.telefono)

    async def enviar(self, destinatario: Destinatario, mensaje: Mensaje) -> None:
        numero = self.direccion_de(destinatario)
        if not numero:
            raise MensajeriaError(f"{destinatario.nombre} no tiene un teléfono utilizable")
        jid = f"{numero}@s.whatsapp.net"

        async with self._cliente() as cliente:
            # El texto va primero y los adjuntos después, cada uno en su
            # llamada: WhatsApp no tiene «cuerpo con adjuntos» como el correo.
            # Si el texto sale y un adjunto no, el destinatario al menos sabe
            # de qué se trata.
            await self._llamar(
                cliente, "/send/message", json={"phone": jid, "message": mensaje.texto}
            )
            for adjunto in mensaje.adjuntos:
                await self._llamar(
                    cliente,
                    "/send/file",
                    data={"phone": jid, "caption": adjunto.nombre_archivo},
                    files={
                        "file": (
                            adjunto.nombre_archivo,
                            adjunto.contenido,
                            adjunto.content_type,
                        )
                    },
                )

    def _cliente(self) -> httpx.AsyncClient:
        config = self._config
        return httpx.AsyncClient(
            base_url=(config.base_url or "").rstrip("/"),
            auth=(config.usuario, config.password or "") if config.usuario else None,
            # Solo hace falta si el puente tiene varias cuentas vinculadas;
            # con una sola, GOWA la toma por defecto y la cabecera sobra.
            headers={"X-Device-Id": config.device_id} if config.device_id else {},
            timeout=_TIEMPO_ESPERA,
        )

    # ── Vinculación por QR (capacidad `VinculacionPorQr`) ───────────────
    #
    # Un puente de WhatsApp Web no tiene credenciales: tiene un móvil
    # emparejado. Todo esto existe para poder emparejarlo desde Ajustes en
    # vez de tener que abrir un túnel contra el puerto del puente.

    async def estado_vinculacion(self) -> Vinculacion:
        async with self._cliente() as cliente:
            try:
                dispositivos = await self._dispositivos(cliente)
            except MensajeriaError:
                # No poder preguntar es, a efectos de quien mira la pantalla,
                # lo mismo que no estar vinculado.
                return Vinculacion(vinculado=False)

        for dispositivo in dispositivos:
            if dispositivo.get("state") == "logged_in":
                return Vinculacion(
                    vinculado=True,
                    descripcion=dispositivo.get("phone_number")
                    or dispositivo.get("display_name"),
                    device_id=dispositivo.get("id"),
                )
        # Hay hueco creado pero sin móvil detrás: se devuelve su id para que
        # el emparejamiento reutilice el mismo y no vaya creando huecos.
        primero = dispositivos[0] if dispositivos else None
        return Vinculacion(
            vinculado=False, device_id=primero.get("id") if primero else None
        )

    async def iniciar_vinculacion(self) -> CodigoQr:
        async with self._cliente() as cliente:
            dispositivos = await self._dispositivos(cliente)
            if dispositivos:
                device_id = dispositivos[0].get("id")
            else:
                creado = await self._pedir(cliente, "POST", "/devices", json={})
                device_id = creado.get("id")
            if not device_id:
                raise MensajeriaError("El puente no ha devuelto ningún dispositivo")

            datos = await self._pedir(cliente, "GET", f"/devices/{device_id}/login")
            enlace = datos.get("qr_link")
            if not enlace:
                raise MensajeriaError("El puente no ha devuelto ningún QR")

            # El enlace apunta al host del PUENTE (`http://localhost:3000/...`),
            # que no es alcanzable ni desde aquí ni desde el navegador de quien
            # configura. Se conserva solo la ruta y se pide contra la dirección
            # que sí tenemos configurada.
            camino = httpx.URL(enlace)
            ruta = camino.path + (f"?{camino.query.decode()}" if camino.query else "")
            try:
                imagen = await cliente.get(ruta)
            except httpx.HTTPError as exc:
                raise MensajeriaError(f"No se ha podido descargar el QR: {exc}") from exc
            if imagen.status_code >= 400:
                raise MensajeriaError(f"El QR devolvió {imagen.status_code}")

            return CodigoQr(
                imagen_png=imagen.content, segundos=int(datos.get("qr_duration") or 30)
            )

    async def desvincular(self) -> None:
        async with self._cliente() as cliente:
            for dispositivo in await self._dispositivos(cliente):
                identificador = dispositivo.get("id")
                if identificador:
                    await self._pedir(cliente, "POST", f"/devices/{identificador}/logout")

    async def _dispositivos(self, cliente: httpx.AsyncClient) -> list[dict]:
        datos = await self._pedir(cliente, "GET", "/devices")
        return datos if isinstance(datos, list) else []

    async def _pedir(self, cliente: httpx.AsyncClient, metodo: str, ruta: str, **kwargs):
        """Como `_llamar`, pero devolviendo el `results` de la respuesta."""
        try:
            respuesta = await cliente.request(metodo, ruta, **kwargs)
        except httpx.HTTPError as exc:
            raise MensajeriaError(f"No se ha podido contactar con WhatsApp: {exc}") from exc
        self._comprobar(respuesta)
        return respuesta.json().get("results")

    async def _llamar(self, cliente: httpx.AsyncClient, ruta: str, **kwargs) -> None:
        try:
            respuesta = await cliente.post(ruta, **kwargs)
        except httpx.HTTPError as exc:
            raise MensajeriaError(f"No se ha podido contactar con WhatsApp: {exc}") from exc
        self._comprobar(respuesta)

    @staticmethod
    def _comprobar(respuesta: httpx.Response) -> None:
        if respuesta.status_code >= 400:
            raise MensajeriaError(
                f"WhatsApp respondió {respuesta.status_code}: {respuesta.text[:300]}"
            )
        try:
            cuerpo = respuesta.json()
        except ValueError:
            raise MensajeriaError("El puente de WhatsApp no devolvió JSON") from None
        if cuerpo.get("code") != _CODIGO_OK:
            raise MensajeriaError(
                str(cuerpo.get("message") or f"WhatsApp devolvió «{cuerpo.get('code')}»")
            )
