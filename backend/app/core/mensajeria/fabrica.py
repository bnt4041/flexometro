"""Composition root de la mensajería: el ÚNICO módulo que sabe qué
adaptadores existen.

Todo lo demás —el circuito de firma, los avisos— pide un canal y recibe algo
con la forma de `ProveedorMensajeria`. Cambiar el puente de WhatsApp Web por
la API oficial se hace aquí y en Ajustes: ni una línea del dominio se entera.

Los imports de configuración van dentro de las funciones a propósito:
`settings_models` vive en `app.modules.core`, cuyo router importa mensajería
a nivel de fichero. Importarlo arriba cerraría el ciclo (ver la nota de
`app.core.mailer`, que documenta el mismo problema con más detalle).
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mensajeria.puerto import Canal, ProveedorMensajeria

logger = logging.getLogger(__name__)


async def proveedor_de(
    session: AsyncSession, organization_id: uuid.UUID, canal: Canal
) -> ProveedorMensajeria | None:
    """El proveedor de ese canal, o None si no hay uno utilizable.

    None es una respuesta normal, no un error: que una instalación no tenga
    WhatsApp configurado es lo esperado, y quien pregunta ya decide con qué
    se queda."""
    if canal == Canal.EMAIL:
        return await _proveedor_email(session, organization_id)
    if canal == Canal.WHATSAPP:
        return await proveedor_whatsapp(session)
    return None


async def canales_disponibles(
    session: AsyncSession, organization_id: uuid.UUID
) -> set[Canal]:
    """Por qué canales se puede mandar algo ahora mismo. Para decidir sin
    llegar a construir un mensaje."""
    return {
        canal
        for canal in Canal
        if await proveedor_de(session, organization_id, canal) is not None
    }


async def _proveedor_email(
    session: AsyncSession, organization_id: uuid.UUID
) -> ProveedorMensajeria | None:
    from app.core.mensajeria.adaptadores.smtp import AdaptadorSmtp
    from app.modules.core.settings_service import configuracion_smtp_de

    try:
        config = await configuracion_smtp_de(session, organization_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se ha podido leer la configuración de SMTP: %s", exc)
        return None
    # `configuracion_smtp_de` devuelve la fila aunque esté vacía; sin host no
    # hay servidor al que hablar.
    return AdaptadorSmtp(config) if config and config.host else None


async def proveedor_whatsapp(
    session: AsyncSession, *, exigir_activa: bool = True
) -> ProveedorMensajeria | None:
    """WhatsApp es de plataforma, no de cada organización, así que se puede
    pedir sin saber de quién es el mensaje — lo usa la prueba de Ajustes.

    `exigir_activa=False` lo devuelve aunque esté apagado. Hace falta para
    poder vincular un móvil ANTES de encenderlo, que es el orden en que se
    configura: nadie activa a ciegas un canal que todavía no funciona."""
    from app.modules.core.settings_models import ProveedorWhatsApp
    from app.modules.core.settings_service import obtener_configuracion_whatsapp

    try:
        config = await obtener_configuracion_whatsapp(session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se ha podido leer la configuración de WhatsApp: %s", exc)
        return None
    if not config or (exigir_activa and not config.activa):
        return None

    if config.proveedor == ProveedorWhatsApp.CLOUD:
        from app.core.mensajeria.adaptadores.whatsapp_cloud import AdaptadorWhatsAppCloud

        if not (config.cloud_phone_number_id and config.cloud_token):
            return None
        return AdaptadorWhatsAppCloud(config)

    from app.core.mensajeria.adaptadores.gowa import AdaptadorGowa

    return AdaptadorGowa(config) if config.base_url else None
