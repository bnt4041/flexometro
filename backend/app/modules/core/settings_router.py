import base64

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.mailer import MailerError, enviar_correo
from app.core.mensajeria import (
    Destinatario,
    Mensaje,
    MensajeriaError,
    VinculacionPorQr,
    proveedor_whatsapp,
)
from app.modules.core import settings_service as service
from app.modules.core.settings_schemas import (
    ConfiguracionIAOut,
    ConfiguracionIAUpdate,
    ConfiguracionPasarelaOut,
    ConfiguracionPasarelaUpdate,
    ConfiguracionSmtpOut,
    ConfiguracionSmtpUpdate,
    ConfiguracionWhatsAppOut,
    ConfiguracionWhatsAppUpdate,
    PruebaSmtpIn,
    PruebaSmtpOut,
    PruebaWhatsAppIn,
    PruebaWhatsAppOut,
    QrVinculacionOut,
    VinculacionWhatsAppOut,
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
        deepseek_vision_model=config.deepseek_vision_model or settings.deepseek_vision_model,
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


def _whatsapp_out(config) -> ConfiguracionWhatsAppOut:
    return ConfiguracionWhatsAppOut(
        # Sin `.value`: el esquema ya lo declara como el enum, así que
        # Pydantic lo serializa bien venga como miembro o como cadena.
        proveedor=config.proveedor,
        activa=config.activa,
        prefijo_pais=config.prefijo_pais,
        base_url=config.base_url,
        usuario=config.usuario,
        device_id=config.device_id,
        tiene_password=bool(config.password),
        cloud_phone_number_id=config.cloud_phone_number_id,
        cloud_version=config.cloud_version,
        plantilla_aviso=config.plantilla_aviso,
        plantilla_codigo=config.plantilla_codigo,
        idioma_plantilla=config.idioma_plantilla,
        tiene_cloud_token=bool(config.cloud_token),
    )


@router.get("/ajustes-whatsapp", response_model=ConfiguracionWhatsAppOut)
async def obtener_ajustes_whatsapp(
    session: AsyncSession = Depends(get_session),
) -> ConfiguracionWhatsAppOut:
    return _whatsapp_out(await service.obtener_configuracion_whatsapp(session))


@router.patch("/ajustes-whatsapp", response_model=ConfiguracionWhatsAppOut)
async def actualizar_ajustes_whatsapp(
    datos: ConfiguracionWhatsAppUpdate, session: AsyncSession = Depends(get_session)
) -> ConfiguracionWhatsAppOut:
    config = await service.actualizar_configuracion_whatsapp(
        session, datos.model_dump(exclude_unset=True)
    )
    return _whatsapp_out(config)


async def _vinculador(session: AsyncSession) -> VinculacionPorQr | None:
    """El proveedor actual SI además sabe vincularse por QR.

    Se pide con `exigir_activa=False` a propósito: primero se vincula el
    móvil y después se enciende el canal, no al revés."""
    proveedor = await proveedor_whatsapp(session, exigir_activa=False)
    return proveedor if isinstance(proveedor, VinculacionPorQr) else None


@router.get("/ajustes-whatsapp/vinculacion", response_model=VinculacionWhatsAppOut)
async def estado_vinculacion_whatsapp(
    session: AsyncSession = Depends(get_session),
) -> VinculacionWhatsAppOut:
    vinculador = await _vinculador(session)
    if vinculador is None:
        # No es un error: la API oficial simplemente no se vincula así.
        return VinculacionWhatsAppOut(soporta_qr=False, vinculado=False)
    try:
        estado = await vinculador.estado_vinculacion()
    except MensajeriaError as exc:
        return VinculacionWhatsAppOut(soporta_qr=True, vinculado=False, error=str(exc))
    return VinculacionWhatsAppOut(
        soporta_qr=True, vinculado=estado.vinculado, descripcion=estado.descripcion
    )


@router.post("/ajustes-whatsapp/vinculacion", response_model=QrVinculacionOut)
async def iniciar_vinculacion_whatsapp(
    session: AsyncSession = Depends(get_session),
) -> QrVinculacionOut:
    """Arranca el emparejamiento y devuelve el QR que hay que escanear con el
    móvil desde WhatsApp → Dispositivos vinculados."""
    vinculador = await _vinculador(session)
    if vinculador is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El proveedor seleccionado no se vincula escaneando un código QR",
        )
    try:
        qr = await vinculador.iniciar_vinculacion()
    except MensajeriaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return QrVinculacionOut(
        imagen=f"data:image/png;base64,{base64.b64encode(qr.imagen_png).decode()}",
        segundos=qr.segundos,
    )


@router.delete("/ajustes-whatsapp/vinculacion", response_model=VinculacionWhatsAppOut)
async def desvincular_whatsapp(
    session: AsyncSession = Depends(get_session),
) -> VinculacionWhatsAppOut:
    """Cierra la sesión del móvil vinculado. Deja el canal sin cuenta detrás,
    así que lo que se estuviera mandando por WhatsApp pasará a ir por correo."""
    vinculador = await _vinculador(session)
    if vinculador is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El proveedor seleccionado no se vincula por QR"
        )
    try:
        await vinculador.desvincular()
    except MensajeriaError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return VinculacionWhatsAppOut(soporta_qr=True, vinculado=False)


@router.post("/ajustes-whatsapp/prueba", response_model=PruebaWhatsAppOut)
async def probar_ajustes_whatsapp(
    datos: PruebaWhatsAppIn, session: AsyncSession = Depends(get_session)
) -> PruebaWhatsAppOut:
    """Manda un WhatsApp real con la configuración YA GUARDADA, igual que la
    prueba de SMTP: se prueba lo que se va a usar, no lo que haya a medio
    escribir en el formulario.

    Va por el puerto de mensajería, así que prueba el proveedor que esté
    seleccionado sin saber cuál es.

    `exigir_activa=False` porque probar es lo que se hace ANTES de encender el
    canal: obligar a activarlo primero sería pedir que se encienda a ciegas
    justo lo que se quiere comprobar."""
    proveedor = await proveedor_whatsapp(session, exigir_activa=False)
    if proveedor is None:
        return PruebaWhatsAppOut(
            enviado=False,
            error="Faltan credenciales de WhatsApp. Guárdalas antes de probar.",
        )
    try:
        await proveedor.enviar(
            Destinatario(nombre="Prueba", telefono=datos.telefono),
            Mensaje(
                asunto="Prueba de WhatsApp",
                texto=(
                    "Mensaje de prueba de Flexómetro. "
                    "Si lo has recibido, WhatsApp está bien configurado."
                ),
                variables=("Flexómetro",),
            ),
        )
    except MensajeriaError as exc:
        return PruebaWhatsAppOut(enviado=False, error=str(exc))
    return PruebaWhatsAppOut(enviado=True)


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
