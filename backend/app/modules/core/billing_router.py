import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.mailer import MailerError, enviar_correo
from app.modules.core import billing_service as service
from app.modules.core import cuenta_service, settings_service
from app.modules.core import service as core_service
from app.modules.core.billing_schemas import (
    AplicacionDescuentoOut,
    AplicarDescuentosIn,
    CosteEstimadoOut,
    DescuentoCreate,
    DescuentoOut,
    DescuentoUpdate,
    TarifaCreate,
    TarifaDetalle,
    TarifaOut,
    TarifaUpdate,
)
from app.modules.core.settings_schemas import (
    ConfiguracionSmtpOut,
    ConfiguracionSmtpUpdate,
    PruebaSmtpIn,
    PruebaSmtpOut,
)

router = APIRouter()


# --- Tarifas ---


@router.get("/tarifas", response_model=list[TarifaOut])
async def listar_tarifas(session: AsyncSession = Depends(get_session)) -> list[TarifaOut]:
    return [TarifaOut.model_validate(t) for t in await service.listar_tarifas(session)]


@router.post("/tarifas", response_model=TarifaDetalle, status_code=status.HTTP_201_CREATED)
async def crear_tarifa(
    datos: TarifaCreate, session: AsyncSession = Depends(get_session)
) -> TarifaDetalle:
    try:
        tarifa = await service.crear_tarifa(session, datos)
    except service.NombreDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TarifaDetalle.model_validate(tarifa)


@router.get("/tarifas/{tarifa_id}", response_model=TarifaDetalle)
async def detalle_tarifa(
    tarifa_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> TarifaDetalle:
    tarifa = await service.obtener_tarifa(session, tarifa_id)
    if tarifa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarifa no encontrada")
    return TarifaDetalle.model_validate(tarifa)


@router.patch("/tarifas/{tarifa_id}", response_model=TarifaDetalle)
async def actualizar_tarifa(
    tarifa_id: uuid.UUID, datos: TarifaUpdate, session: AsyncSession = Depends(get_session)
) -> TarifaDetalle:
    tarifa = await service.actualizar_tarifa(session, tarifa_id, datos)
    if tarifa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarifa no encontrada")
    return TarifaDetalle.model_validate(tarifa)


# --- Descuentos ---


@router.get("/descuentos", response_model=list[DescuentoOut])
async def listar_descuentos(
    tarifa_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[DescuentoOut]:
    descuentos = await service.listar_descuentos(session, tarifa_id=tarifa_id)
    return [DescuentoOut.model_validate(d) for d in descuentos]


@router.post("/descuentos", response_model=DescuentoOut, status_code=status.HTTP_201_CREATED)
async def crear_descuento(
    datos: DescuentoCreate, session: AsyncSession = Depends(get_session)
) -> DescuentoOut:
    try:
        descuento = await service.crear_descuento(session, datos)
    except service.DescuentoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return DescuentoOut.model_validate(descuento)


@router.patch("/descuentos/{descuento_id}", response_model=DescuentoOut)
async def actualizar_descuento(
    descuento_id: uuid.UUID, datos: DescuentoUpdate, session: AsyncSession = Depends(get_session)
) -> DescuentoOut:
    descuento = await service.actualizar_descuento(session, descuento_id, datos)
    if descuento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Descuento no encontrado")
    return DescuentoOut.model_validate(descuento)


@router.delete("/descuentos/{descuento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_descuento(
    descuento_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    if not await service.eliminar_descuento(session, descuento_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Descuento no encontrado")


# --- Aplicación de descuentos del catálogo a una cuenta ---


def _aplicacion_out(aplicacion) -> AplicacionDescuentoOut:
    from datetime import date as _date

    return AplicacionDescuentoOut(
        id=aplicacion.id,
        cuenta_id=aplicacion.cuenta_id,
        descuento=DescuentoOut.model_validate(aplicacion.descuento),
        aplicado_en=aplicacion.aplicado_en,
        anulado_en=aplicacion.anulado_en,
        vigente=service.aplicacion_vigente(aplicacion, _date.today()),
    )


@router.get("/cuentas/{cuenta_id}/descuentos", response_model=list[AplicacionDescuentoOut])
async def listar_aplicaciones_descuento(
    cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[AplicacionDescuentoOut]:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    aplicaciones = await service.listar_aplicaciones(session, cuenta_id)
    return [_aplicacion_out(a) for a in aplicaciones]


@router.post(
    "/cuentas/{cuenta_id}/descuentos",
    response_model=list[AplicacionDescuentoOut],
    status_code=status.HTTP_201_CREATED,
)
async def aplicar_descuentos(
    cuenta_id: uuid.UUID,
    datos: AplicarDescuentosIn,
    session: AsyncSession = Depends(get_session),
) -> list[AplicacionDescuentoOut]:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    try:
        aplicaciones = await service.aplicar_descuentos(session, cuenta_id, datos.descuento_ids)
    except service.DescuentoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except service.AplicacionYaVigente as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return [_aplicacion_out(a) for a in aplicaciones]


@router.post(
    "/cuentas/{cuenta_id}/descuentos/{aplicacion_id}/anular",
    response_model=AplicacionDescuentoOut,
)
async def anular_aplicacion_descuento(
    cuenta_id: uuid.UUID,
    aplicacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AplicacionDescuentoOut:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    try:
        aplicacion = await service.anular_aplicacion(session, aplicacion_id)
    except service.AplicacionNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _aplicacion_out(aplicacion)


# --- Cobros y uso de IA de una cuenta ---


class CobroCreateIn(BaseModel):
    concepto: str = Field(min_length=1, max_length=250)
    importe: Decimal = Field(gt=0)
    fecha: date
    notas: str | None = None


class CobroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cuenta_id: uuid.UUID
    concepto: str
    importe: Decimal
    fecha: date
    origen: str
    referencia_externa: str | None
    notas: str | None


class UsoIAOut(BaseModel):
    id: uuid.UUID
    usuario_subject: str
    usuario_nombre: str
    proveedor: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    referencia: str | None
    created_at: str


@router.get("/cuentas/{cuenta_id}/cobros", response_model=list[CobroOut])
async def listar_cobros(
    cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[CobroOut]:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    return [CobroOut.model_validate(c) for c in await service.listar_cobros(session, cuenta_id)]


@router.post(
    "/cuentas/{cuenta_id}/cobros",
    response_model=CobroOut,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_cobro(
    cuenta_id: uuid.UUID, datos: CobroCreateIn, session: AsyncSession = Depends(get_session)
) -> CobroOut:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    cobro = await service.registrar_cobro(
        session,
        cuenta_id,
        concepto=datos.concepto,
        importe=datos.importe,
        fecha=datos.fecha,
        notas=datos.notas,
    )
    return CobroOut.model_validate(cobro)


@router.get("/cuentas/{cuenta_id}/uso-ia", response_model=list[UsoIAOut])
async def listar_uso_ia(
    cuenta_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[UsoIAOut]:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    items, _ = await service.listar_uso_ia_de_cuenta(session, cuenta_id, limit=limit, offset=offset)
    return [
        UsoIAOut(
            id=u.id,
            usuario_subject=u.usuario_subject,
            usuario_nombre=u.usuario_nombre,
            proveedor=u.proveedor.value,
            modelo=u.modelo,
            tokens_entrada=u.tokens_entrada,
            tokens_salida=u.tokens_salida,
            referencia=u.referencia,
            created_at=u.created_at.isoformat(),
        )
        for u in items
    ]


@router.get("/cuentas/{cuenta_id}/coste-estimado", response_model=CosteEstimadoOut)
async def coste_estimado(
    cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> CosteEstimadoOut:
    cuenta = await cuenta_service.obtener_cuenta(session, cuenta_id)
    if cuenta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")

    tarifa = await service.obtener_tarifa(session, cuenta.tarifa_id) if cuenta.tarifa_id else None
    modulos_activos = await service.modulos_activos_de_cuenta(session, cuenta_id)
    tokens_deepseek, tokens_gemini = await service.tokens_del_mes_de_cuenta(session, cuenta_id)
    aplicaciones = await service.listar_aplicaciones(session, cuenta_id)

    resultado = service.calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos=modulos_activos,
        tokens_deepseek=tokens_deepseek,
        tokens_gemini=tokens_gemini,
        aplicaciones=aplicaciones,
    )
    return CosteEstimadoOut(
        tarifa_nombre=tarifa.nombre if tarifa else None,
        tokens_deepseek_mes=tokens_deepseek,
        tokens_gemini_mes=tokens_gemini,
        **resultado,
    )


# --- SMTP propio de una organización ---


def _smtp_out(config) -> ConfiguracionSmtpOut:
    return ConfiguracionSmtpOut(
        host=config.host,
        puerto=config.puerto,
        usuario=config.usuario,
        remitente=config.remitente,
        usa_tls=config.usa_tls,
        tiene_password=bool(config.password),
    )


@router.get("/organizaciones/{organization_id}/smtp", response_model=ConfiguracionSmtpOut)
async def obtener_smtp_organizacion(
    organization_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ConfiguracionSmtpOut:
    if await core_service.obtener_organizacion(session, organization_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    config = await settings_service.obtener_configuracion_smtp_organizacion(session, organization_id)
    return _smtp_out(config)


@router.patch("/organizaciones/{organization_id}/smtp", response_model=ConfiguracionSmtpOut)
async def actualizar_smtp_organizacion(
    organization_id: uuid.UUID,
    datos: ConfiguracionSmtpUpdate,
    session: AsyncSession = Depends(get_session),
) -> ConfiguracionSmtpOut:
    if await core_service.obtener_organizacion(session, organization_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    config = await settings_service.actualizar_configuracion_smtp_organizacion(
        session, organization_id, datos.model_dump(exclude_unset=True)
    )
    return _smtp_out(config)


@router.post("/organizaciones/{organization_id}/smtp/prueba", response_model=PruebaSmtpOut)
async def probar_smtp_organizacion(
    organization_id: uuid.UUID,
    datos: PruebaSmtpIn,
    session: AsyncSession = Depends(get_session),
) -> PruebaSmtpOut:
    if await core_service.obtener_organizacion(session, organization_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    config = await settings_service.obtener_configuracion_smtp_organizacion(session, organization_id)
    try:
        await enviar_correo(
            config,
            destinatario=datos.destinatario,
            asunto="Correo de prueba — Flexómetro",
            cuerpo_html="<p>Si has recibido este correo, el SMTP propio de esta organización funciona correctamente.</p>",
        )
    except MailerError as exc:
        return PruebaSmtpOut(enviado=False, error=str(exc))
    return PruebaSmtpOut(enviado=True)
