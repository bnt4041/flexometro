import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut
from app.modules.facturacion import informes, service, ventas_concepto, webhook
from app.modules.facturacion.models import Certificacion, EstadoFactura, Factura
from app.modules.facturacion.schemas import (
    AnularFactura,
    CertificacionCreate,
    CertificacionDetalle,
    CertificacionLineaOut,
    CertificacionOut,
    CertificacionUpdate,
    CobroCreate,
    CobroOut,
    FacturaDetalle,
    FacturaOut,
    FacturaResumen,
    FacturaSuelta,
    FacturaUpdate,
    GenerarDesdeCertificacion,
)
from app.modules.presupuestos.schemas import VentasOut

guard = Depends(require_module("facturacion"))

certificaciones_router = APIRouter(
    prefix="/api/certificaciones", tags=["facturacion"], dependencies=[guard]
)
facturas_router = APIRouter(prefix="/api/facturas", tags=["facturacion"], dependencies=[guard])
cobros_router = APIRouter(prefix="/api/cobros", tags=["facturacion"], dependencies=[guard])
# Prefijo /api/conceptos a propósito, igual que /api/obras en compras/costes.py:
# el cruce vive aquí porque facturacion es el único módulo que puede ver a la
# vez la partida y su certificación, pero la URL habla del concepto que el
# usuario está consultando en su ficha del banco de precios.
ventas_router = APIRouter(prefix="/api/conceptos", tags=["facturacion"], dependencies=[guard])


def _excepciones_certificacion(exc: Exception) -> HTTPException:
    if isinstance(exc, service.CertificacionBloqueada):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


async def _detalle_certificacion(session: AsyncSession, certificacion) -> CertificacionDetalle:
    importes = service.importes_certificacion(certificacion)
    facturada = await service.certificacion_facturada(session, certificacion.id)
    return CertificacionDetalle(
        **CertificacionOut.model_validate(certificacion).model_dump(),
        lineas=[CertificacionLineaOut.model_validate(l) for l in certificacion.lineas],
        facturada=facturada,
        **importes,
    )


@certificaciones_router.get("", response_model=Page[CertificacionOut])
async def listar_certificaciones(
    obra_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> Page[CertificacionOut]:
    items, total = await service.listar_certificaciones(
        session,
        obra_id=obra_id,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[CertificacionOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@certificaciones_router.post(
    "", response_model=CertificacionDetalle, status_code=status.HTTP_201_CREATED
)
async def crear_certificacion(
    datos: CertificacionCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> CertificacionDetalle:
    try:
        certificacion = await service.crear_certificacion(session, datos)
    except (
        service.ObraInvalida,
        service.PartidaInvalida,
        service.CertificacionInvalida,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return await _detalle_certificacion(session, certificacion)


async def _certificacion_propia(
    session: AsyncSession, certificacion_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    certificacion = await service.obtener_certificacion(session, certificacion_id)
    if certificacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Certificación no encontrada"
        )
    verificar_propiedad(alcance, principal, certificacion.creado_por_subject)
    return certificacion


@certificaciones_router.get("/{certificacion_id}", response_model=CertificacionDetalle)
async def detalle_certificacion(
    certificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> CertificacionDetalle:
    certificacion = await _certificacion_propia(session, certificacion_id, alcance, principal)
    return await _detalle_certificacion(session, certificacion)


@certificaciones_router.get(
    "/{certificacion_id}/historial", response_model=list[RegistroAuditoriaOut]
)
async def historial_certificacion(
    certificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> list[RegistroAuditoriaOut]:
    await _certificacion_propia(session, certificacion_id, alcance, principal)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Certificacion), registro_id=certificacion_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@certificaciones_router.patch("/{certificacion_id}", response_model=CertificacionDetalle)
async def actualizar_certificacion(
    certificacion_id: uuid.UUID,
    datos: CertificacionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> CertificacionDetalle:
    await _certificacion_propia(session, certificacion_id, alcance, principal)
    try:
        certificacion = await service.actualizar_certificacion(session, certificacion_id, datos)
    except service.CertificacionBloqueada as exc:
        raise _excepciones_certificacion(exc) from exc
    assert certificacion is not None
    return await _detalle_certificacion(session, certificacion)


@certificaciones_router.delete("/{certificacion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_certificacion(
    certificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> None:
    await _certificacion_propia(session, certificacion_id, alcance, principal)
    try:
        await service.eliminar_certificacion(session, certificacion_id)
    except service.CertificacionBloqueada as exc:
        raise _excepciones_certificacion(exc) from exc


@certificaciones_router.post("/{certificacion_id}/emitir", response_model=CertificacionDetalle)
async def emitir_certificacion(
    certificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> CertificacionDetalle:
    await _certificacion_propia(session, certificacion_id, alcance, principal)
    certificacion = await service.emitir_certificacion(session, certificacion_id)
    assert certificacion is not None
    return await _detalle_certificacion(session, certificacion)


@certificaciones_router.post(
    "/{certificacion_id}/factura", response_model=FacturaOut, status_code=status.HTTP_201_CREATED
)
async def generar_factura(
    certificacion_id: uuid.UUID,
    datos: GenerarDesdeCertificacion,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaOut:
    await _certificacion_propia(session, certificacion_id, alcance, principal)
    try:
        factura = await service.generar_factura_desde_certificacion(
            session, certificacion_id, datos
        )
    except (service.CertificacionBloqueada, service.ObraInvalida) as exc:
        raise _excepciones_certificacion(exc) from exc
    assert factura is not None
    return FacturaOut.model_validate(factura)


@certificaciones_router.get("/{certificacion_id}/pdf")
async def pdf_certificacion(
    certificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> Response:
    certificacion = await _certificacion_propia(session, certificacion_id, alcance, principal)
    pdf = await informes.generar_certificacion(session, certificacion)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{certificacion.codigo}.pdf"'
        },
    )


# --- Facturas ---


def _resumen_factura(factura, razon_social: str) -> FacturaResumen:
    cobrado, pendiente, situacion, vencida = service.situacion_cobro(factura)
    return FacturaResumen(
        **FacturaOut.model_validate(factura).model_dump(),
        cliente_razon_social=razon_social,
        cobrado=cobrado,
        pendiente=pendiente,
        situacion_cobro=situacion,
        vencida=vencida,
    )


@facturas_router.get("", response_model=Page[FacturaResumen])
async def listar_facturas(
    obra_id: uuid.UUID | None = None,
    estado: EstadoFactura | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> Page[FacturaResumen]:
    filas, total = await service.listar_facturas(
        session,
        obra_id=obra_id,
        estado=estado.value if estado else None,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    items = [_resumen_factura(f, razon) for f, razon in filas]
    return Page(items=items, total=total, limit=limit, offset=offset)


@facturas_router.post("", response_model=FacturaOut, status_code=status.HTTP_201_CREATED)
async def crear_factura_suelta(
    datos: FacturaSuelta,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaOut:
    try:
        factura = await service.crear_factura_suelta(session, datos)
    except service.ObraInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return FacturaOut.model_validate(factura)


async def _factura_propia(
    session: AsyncSession, factura_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    resultado = await service.obtener_factura(session, factura_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada")
    factura, razon_social = resultado
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    return factura, razon_social


@facturas_router.get("/{factura_id}", response_model=FacturaDetalle)
async def detalle_factura(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> FacturaDetalle:
    factura, razon_social = await _factura_propia(session, factura_id, alcance, principal)
    resumen = _resumen_factura(factura, razon_social)
    return FacturaDetalle(
        **resumen.model_dump(),
        cobros=[CobroOut.model_validate(c) for c in factura.cobros],
    )


@facturas_router.get("/{factura_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial_factura(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> list[RegistroAuditoriaOut]:
    await _factura_propia(session, factura_id, alcance, principal)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Factura), registro_id=factura_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@facturas_router.patch("/{factura_id}", response_model=FacturaOut)
async def actualizar_factura(
    factura_id: uuid.UUID,
    datos: FacturaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaOut:
    await _factura_propia(session, factura_id, alcance, principal)
    try:
        factura = await service.actualizar_factura(session, factura_id, datos)
    except service.FacturaNoEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    assert factura is not None
    return FacturaOut.model_validate(factura)


@facturas_router.delete("/{factura_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_factura(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> None:
    await _factura_propia(session, factura_id, alcance, principal)
    try:
        await service.eliminar_factura(session, factura_id)
    except service.FacturaNoEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@facturas_router.post("/{factura_id}/emitir", response_model=FacturaOut)
async def emitir_factura(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaOut:
    await _factura_propia(session, factura_id, alcance, principal)
    try:
        factura = await service.emitir_factura(session, factura_id)
    except service.FacturaNoEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    assert factura is not None

    # Best-effort: si n8n no responde, la factura sigue válidamente emitida y
    # numerada; solo queda pendiente de notificar.
    await webhook.notificar_emision(session, factura)
    return FacturaOut.model_validate(factura)


@facturas_router.post("/{factura_id}/notificar", response_model=FacturaOut)
async def reintentar_notificacion(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaOut:
    factura, _ = await _factura_propia(session, factura_id, alcance, principal)
    if factura.estado != EstadoFactura.EMITIDA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se notifican facturas emitidas",
        )
    await webhook.notificar_emision(session, factura)
    return FacturaOut.model_validate(factura)


@facturas_router.post("/{factura_id}/anular", response_model=FacturaOut)
async def anular_factura(
    factura_id: uuid.UUID,
    datos: AnularFactura,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaOut:
    await _factura_propia(session, factura_id, alcance, principal)
    try:
        factura = await service.anular_factura(session, factura_id, datos.motivo)
    except service.FacturaNoEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    assert factura is not None
    return FacturaOut.model_validate(factura)


@facturas_router.get("/{factura_id}/pdf")
async def pdf_factura(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> Response:
    factura, razon_social = await _factura_propia(session, factura_id, alcance, principal)
    pdf = await informes.generar_factura(session, factura, razon_social)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{factura.codigo}.pdf"'},
    )


@facturas_router.post(
    "/{factura_id}/cobros", response_model=CobroOut, status_code=status.HTTP_201_CREATED
)
async def registrar_cobro(
    factura_id: uuid.UUID,
    datos: CobroCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> CobroOut:
    await _factura_propia(session, factura_id, alcance, principal)
    try:
        cobro = await service.registrar_cobro(session, factura_id, datos)
    except service.FacturaNoEditable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    assert cobro is not None
    return CobroOut.model_validate(cobro)


@cobros_router.delete("/{cobro_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_cobro(
    cobro_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> None:
    cobro = await service.obtener_cobro(session, cobro_id)
    if cobro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cobro no encontrado")
    await _factura_propia(session, cobro.factura_id, alcance, principal)
    await service.eliminar_cobro(session, cobro_id)


@ventas_router.get("/{concepto_id}/ventas", response_model=VentasOut)
async def ventas_de_concepto(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> VentasOut:
    return await ventas_concepto.ventas_de_concepto(session, concepto_id)


router = APIRouter()
router.include_router(certificaciones_router)
router.include_router(facturas_router)
router.include_router(cobros_router)
router.include_router(ventas_router)
