"""Ajustes globales de la plataforma: claves de IA, SMTP propio y pasarela de
pago. Cada tabla es de una sola fila (`id` fijo a 1): "obtener" siempre crea
esa fila con los valores por defecto si todavía no existe, para que el resto
del código nunca tenga que distinguir entre "no configurado" y "no existe la
fila".
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core.settings_models import (
    ConfiguracionIA,
    ConfiguracionPasarelaPago,
    ConfiguracionSmtpOrganizacion,
    ConfiguracionSmtpPlataforma,
    ConfiguracionWhatsApp,
)


async def obtener_configuracion_ia(session: AsyncSession) -> ConfiguracionIA:
    config = await session.get(ConfiguracionIA, 1)
    if config is None:
        config = ConfiguracionIA(id=1)
        session.add(config)
        await session.flush()
    return config


async def actualizar_configuracion_ia(session: AsyncSession, datos: dict) -> ConfiguracionIA:
    config = await obtener_configuracion_ia(session)
    for campo, valor in datos.items():
        setattr(config, campo, valor)
    await session.flush()
    return config


async def obtener_configuracion_smtp_plataforma(
    session: AsyncSession,
) -> ConfiguracionSmtpPlataforma:
    config = await session.get(ConfiguracionSmtpPlataforma, 1)
    if config is None:
        config = ConfiguracionSmtpPlataforma(id=1)
        session.add(config)
        await session.flush()
    return config


async def actualizar_configuracion_smtp_plataforma(
    session: AsyncSession, datos: dict
) -> ConfiguracionSmtpPlataforma:
    config = await obtener_configuracion_smtp_plataforma(session)
    for campo, valor in datos.items():
        setattr(config, campo, valor)
    await session.flush()
    return config


async def obtener_configuracion_whatsapp(session: AsyncSession) -> ConfiguracionWhatsApp:
    config = await session.get(ConfiguracionWhatsApp, 1)
    if config is None:
        config = ConfiguracionWhatsApp(id=1)
        session.add(config)
        await session.flush()
    return config


async def actualizar_configuracion_whatsapp(
    session: AsyncSession, datos: dict
) -> ConfiguracionWhatsApp:
    config = await obtener_configuracion_whatsapp(session)
    for campo, valor in datos.items():
        setattr(config, campo, valor)
    await session.flush()
    return config


async def obtener_configuracion_pasarela_pago(
    session: AsyncSession,
) -> ConfiguracionPasarelaPago:
    config = await session.get(ConfiguracionPasarelaPago, 1)
    if config is None:
        config = ConfiguracionPasarelaPago(id=1)
        session.add(config)
        await session.flush()
    return config


async def actualizar_configuracion_pasarela_pago(
    session: AsyncSession, datos: dict
) -> ConfiguracionPasarelaPago:
    config = await obtener_configuracion_pasarela_pago(session)
    for campo, valor in datos.items():
        setattr(config, campo, valor)
    await session.flush()
    return config


async def obtener_configuracion_smtp_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> ConfiguracionSmtpOrganizacion:
    config = await session.get(ConfiguracionSmtpOrganizacion, organization_id)
    if config is None:
        config = ConfiguracionSmtpOrganizacion(organization_id=organization_id)
        session.add(config)
        await session.flush()
    return config


async def configuracion_smtp_de(
    session: AsyncSession, organization_id: uuid.UUID
) -> ConfiguracionSmtpOrganizacion | ConfiguracionSmtpPlataforma:
    """La que de verdad hay que usar para mandar un correo en nombre de esta
    organización: la suya propia si la ha configurado, si no la de
    plataforma. Mismo criterio ya usado en `crm.service.enviar_email`,
    reunido aquí para no repetirlo cada vez que un módulo nuevo necesite
    mandar correo."""
    propia = await obtener_configuracion_smtp_organizacion(session, organization_id)
    if propia.host:
        return propia
    return await obtener_configuracion_smtp_plataforma(session)


async def actualizar_configuracion_smtp_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, datos: dict
) -> ConfiguracionSmtpOrganizacion:
    config = await obtener_configuracion_smtp_organizacion(session, organization_id)
    for campo, valor in datos.items():
        setattr(config, campo, valor)
    await session.flush()
    return config
