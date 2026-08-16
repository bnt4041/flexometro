from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.mailer import MailerError, enviar_correo
from app.modules.core import settings_service as service
from app.modules.core.settings_schemas import (
    ConfiguracionIAOut,
    ConfiguracionIAUpdate,
    ConfiguracionPasarelaOut,
    ConfiguracionPasarelaUpdate,
    ConfiguracionSmtpOut,
    ConfiguracionSmtpUpdate,
    PruebaSmtpIn,
    PruebaSmtpOut,
)

router = APIRouter()


def _ia_out(config) -> ConfiguracionIAOut:
    # Estado EFECTIVO (BD con prioridad, .env como respaldo) — es lo que de
    # verdad se usa al llamar a DeepSeek/Gemini (ver credenciales.py), no solo
    # lo que hay guardado en esta tabla. Mostrar solo la fila de BD confundiría
    # a quien vea "no configurada" con una clave real funcionando desde el
    # .env de arranque.
    settings = get_settings()
    return ConfiguracionIAOut(
        deepseek_configurada=bool(config.deepseek_api_key or settings.deepseek_api_key),
        deepseek_model=config.deepseek_model or settings.deepseek_model,
        deepseek_base_url=config.deepseek_base_url or settings.deepseek_base_url,
        gemini_configurada=bool(config.gemini_api_key or settings.gemini_api_key),
        gemini_model=config.gemini_model or settings.gemini_model,
        gemini_base_url=config.gemini_base_url or settings.gemini_base_url,
    )


@router.get("/ajustes-ia", response_model=ConfiguracionIAOut)
async def obtener_ajustes_ia(session: AsyncSession = Depends(get_session)) -> ConfiguracionIAOut:
    return _ia_out(await service.obtener_configuracion_ia(session))


@router.patch("/ajustes-ia", response_model=ConfiguracionIAOut)
async def actualizar_ajustes_ia(
    datos: ConfiguracionIAUpdate, session: AsyncSession = Depends(get_session)
) -> ConfiguracionIAOut:
    config = await service.actualizar_configuracion_ia(
        session, datos.model_dump(exclude_unset=True)
    )
    return _ia_out(config)


def _smtp_out(config) -> ConfiguracionSmtpOut:
    return ConfiguracionSmtpOut(
        host=config.host,
        puerto=config.puerto,
        usuario=config.usuario,
        remitente=config.remitente,
        usa_tls=config.usa_tls,
        tiene_password=bool(config.password),
    )


@router.get("/ajustes-smtp", response_model=ConfiguracionSmtpOut)
async def obtener_ajustes_smtp(
    session: AsyncSession = Depends(get_session),
) -> ConfiguracionSmtpOut:
    return _smtp_out(await service.obtener_configuracion_smtp_plataforma(session))


@router.patch("/ajustes-smtp", response_model=ConfiguracionSmtpOut)
async def actualizar_ajustes_smtp(
    datos: ConfiguracionSmtpUpdate, session: AsyncSession = Depends(get_session)
) -> ConfiguracionSmtpOut:
    config = await service.actualizar_configuracion_smtp_plataforma(
        session, datos.model_dump(exclude_unset=True)
    )
    return _smtp_out(config)


@router.post("/ajustes-smtp/prueba", response_model=PruebaSmtpOut)
async def probar_ajustes_smtp(
    datos: PruebaSmtpIn, session: AsyncSession = Depends(get_session)
) -> PruebaSmtpOut:
    """Envía un correo real con la configuración YA GUARDADA (no la que haya
    a medio escribir en el formulario todavía) — igual que el correo de
    bienvenida usa esta misma configuración, así se prueba lo que de verdad
    se va a usar, no un valor aparte que luego diverja."""
    config = await service.obtener_configuracion_smtp_plataforma(session)
    try:
        await enviar_correo(
            config,
            destinatario=datos.destinatario,
            asunto="Correo de prueba — Flexómetro",
            cuerpo_html="<p>Si has recibido este correo, el SMTP de la plataforma funciona correctamente.</p>",
        )
    except MailerError as exc:
        return PruebaSmtpOut(enviado=False, error=str(exc))
    return PruebaSmtpOut(enviado=True)


def _pasarela_out(config) -> ConfiguracionPasarelaOut:
    return ConfiguracionPasarelaOut(
        proveedor=config.proveedor,
        vendor_id=config.vendor_id,
        tiene_api_key=bool(config.api_key),
        activa=config.activa,
    )


@router.get("/pasarela-pago", response_model=ConfiguracionPasarelaOut)
async def obtener_pasarela_pago(
    session: AsyncSession = Depends(get_session),
) -> ConfiguracionPasarelaOut:
    return _pasarela_out(await service.obtener_configuracion_pasarela_pago(session))


@router.patch("/pasarela-pago", response_model=ConfiguracionPasarelaOut)
async def actualizar_pasarela_pago(
    datos: ConfiguracionPasarelaUpdate, session: AsyncSession = Depends(get_session)
) -> ConfiguracionPasarelaOut:
    config = await service.actualizar_configuracion_pasarela_pago(
        session, datos.model_dump(exclude_unset=True)
    )
    return _pasarela_out(config)
