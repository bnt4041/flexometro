import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.mailer import MailerError
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.compras import costes, oferta_service, service, solicitud_service
from app.modules.compras.models import SolicitudLinea
from app.modules.compras.publico_router import router as publico_router
from app.modules.compras.schemas import (
    AlbaranCreate,
    AlbaranDetalle,
    AlbaranLineaCreate,
    AlbaranLineaOut,
    AlbaranLineaUpdate,
    AlbaranOut,
    AlbaranResumen,
    AlbaranUpdate,
    InformeCosteObra,
)
from app.modules.compras.solicitud_schemas import (
    EnlaceOut,
    LineasActualizar,
    SolicitudActualizar,
    SolicitudConEnlaceOut,
    SolicitudCrear,
    SolicitudLineaOut,
    SolicitudOut,
)
from app.modules.terceros.models import Tercero

guard = Depends(require_module("compras"))

albaranes_router = APIRouter(prefix="/api/albaranes", tags=["compras"], dependencies=[guard])
lineas_router = APIRouter(
    prefix="/api/albaranes-lineas", tags=["compras"], dependencies=[guard]
)
# Prefijo /api/obras a propósito: el informe cruza datos de obras + compras +
# presupuestos, y compras es el único módulo con permiso para conocer los
# tres (ver costes.py). El router vive aquí; la URL habla de "obras" porque es
# lo que el usuario está consultando.
costes_router = APIRouter(prefix="/api/obras", tags=["compras"], dependencies=[guard])
solicitudes_router = APIRouter(
    prefix="/api/solicitudes-precios", tags=["compras"], dependencies=[guard]
)


@albaranes_router.get("", response_model=Page[AlbaranResumen])
async def listar(
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> Page[AlbaranResumen]:
    filas, total = await service.listar_albaranes(
        session,
        obra_id=obra_id,
        proveedor_id=proveedor_id,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    totales = await service.totales_de_albaranes(session, [a.id for a, _ in filas])
    items = [
        AlbaranResumen(
            **AlbaranOut.model_validate(albaran).model_dump(),
            proveedor_razon_social=razon_social,
            total=totales.get(albaran.id, Decimal("0.00")),
        )
        for albaran, razon_social in filas
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@albaranes_router.post("", response_model=AlbaranDetalle, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: AlbaranCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranDetalle:
    try:
        albaran = await service.crear_albaran(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        service.ObraInvalida,
        service.ProveedorInvalido,
        service.ConceptoInvalido,
        service.LineaSinDatos,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    resultado = await service.obtener_albaran(session, albaran.id)
    albaran, razon_social = resultado
    return AlbaranDetalle(
        **AlbaranOut.model_validate(albaran).model_dump(),
        proveedor_razon_social=razon_social,
        lineas=[AlbaranLineaOut.model_validate(l) for l in albaran.lineas],
        total=service.total_de(albaran.lineas),
    )


async def _albaran_propio(
    session: AsyncSession, albaran_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    resultado = await service.obtener_albaran(session, albaran_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Albarán no encontrado")
    albaran, razon_social = resultado
    verificar_propiedad(alcance, principal, albaran.creado_por_subject)
    return albaran, razon_social


@albaranes_router.get("/{albaran_id}", response_model=AlbaranDetalle)
async def detalle(
    albaran_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> AlbaranDetalle:
    albaran, razon_social = await _albaran_propio(session, albaran_id, alcance, principal)
    return AlbaranDetalle(
        **AlbaranOut.model_validate(albaran).model_dump(),
        proveedor_razon_social=razon_social,
        lineas=[AlbaranLineaOut.model_validate(l) for l in albaran.lineas],
        total=service.total_de(albaran.lineas),
    )


@albaranes_router.patch("/{albaran_id}", response_model=AlbaranOut)
async def actualizar(
    albaran_id: uuid.UUID,
    datos: AlbaranUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranOut:
    await _albaran_propio(session, albaran_id, alcance, principal)
    albaran = await service.actualizar_albaran(session, albaran_id, datos)
    return AlbaranOut.model_validate(albaran)


@albaranes_router.delete("/{albaran_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    albaran_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _albaran_propio(session, albaran_id, alcance, principal)
    await service.eliminar_albaran(session, albaran_id)


@albaranes_router.post(
    "/{albaran_id}/lineas", response_model=AlbaranLineaOut, status_code=status.HTTP_201_CREATED
)
async def anadir_linea(
    albaran_id: uuid.UUID,
    datos: AlbaranLineaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranLineaOut:
    await _albaran_propio(session, albaran_id, alcance, principal)
    try:
        linea = await service.anadir_linea(session, albaran_id, datos)
    except (service.ConceptoInvalido, service.LineaSinDatos) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert linea is not None
    return AlbaranLineaOut.model_validate(linea)


async def _linea_propia(
    session: AsyncSession, linea_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    linea = await service.obtener_linea(session, linea_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    await _albaran_propio(session, linea.albaran_id, alcance, principal)
    return linea


@lineas_router.patch("/{linea_id}", response_model=AlbaranLineaOut)
async def actualizar_linea(
    linea_id: uuid.UUID,
    datos: AlbaranLineaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranLineaOut:
    await _linea_propia(session, linea_id, alcance, principal)
    linea = await service.actualizar_linea(session, linea_id, datos)
    assert linea is not None
    return AlbaranLineaOut.model_validate(linea)


@lineas_router.delete("/{linea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_linea(
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _linea_propia(session, linea_id, alcance, principal)
    await service.eliminar_linea(session, linea_id)


@costes_router.get("/{obra_id}/costes", response_model=InformeCosteObra)
async def coste_real_vs_presupuestado(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> InformeCosteObra:
    from app.modules.obras.service import obtener_obra

    obra = await obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    verificar_propiedad(alcance, principal, obra.creado_por_subject)
    informe = await costes.informe_coste(session, obra_id)
    assert informe is not None
    return informe


# --- Solicitud de precios a proveedor ---


async def _solicitud_out(
    session: AsyncSession,
    solicitud,
    *,
    con_lineas: bool = False,
    proveedor: Tercero | None = None,
) -> SolicitudOut:
    if proveedor is None:
        proveedor = await session.get(Tercero, solicitud.proveedor_id)
    lineas: list[SolicitudLineaOut] = []
    if con_lineas:
        filas = (
            await session.execute(
                select(SolicitudLinea)
                .where(SolicitudLinea.solicitud_id == solicitud.id)
                .order_by(SolicitudLinea.orden)
            )
        ).scalars()
        lineas = [SolicitudLineaOut.model_validate(l) for l in filas]
    return SolicitudOut(
        id=solicitud.id,
        codigo=solicitud.codigo,
        presupuesto_id=solicitud.presupuesto_id,
        proveedor_id=solicitud.proveedor_id,
        proveedor_razon_social=proveedor.razon_social if proveedor else "",
        proveedor_email=proveedor.email if proveedor else None,
        estado=solicitud.estado,
        fecha_limite=solicitud.fecha_limite,
        enviada_en=solicitud.enviada_en,
        respondida_en=solicitud.respondida_en,
        notas=solicitud.notas,
        oferta_presupuesto_id=solicitud.oferta_presupuesto_id,
        lineas=lineas,
    )


async def _solicitud_o_404(session: AsyncSession, solicitud_id: uuid.UUID):
    solicitud = await solicitud_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")
    return solicitud


@solicitudes_router.post("", response_model=SolicitudOut, status_code=status.HTTP_201_CREATED)
async def crear_solicitud(
    datos: SolicitudCrear,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    """Deja la solicitud en borrador — no manda nada todavía. Se completa y
    se envía desde la pestaña Comparativo (`PATCH .../lineas`, `PATCH .../`,
    `POST .../enviar`)."""
    try:
        solicitud = await solicitud_service.crear_solicitud(
            session,
            presupuesto_id=datos.presupuesto_id,
            proveedor_id=datos.proveedor_id,
            partida_ids=datos.partida_ids,
            fecha_limite=datos.fecha_limite,
            notas=datos.notas,
        )
    except (
        solicitud_service.PresupuestoInvalido,
        solicitud_service.ProveedorInvalido,
        solicitud_service.SinPartidas,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await session.commit()
    return await _solicitud_out(session, solicitud)


@solicitudes_router.patch("/{solicitud_id}", response_model=SolicitudOut)
async def actualizar_solicitud(
    solicitud_id: uuid.UUID,
    datos: SolicitudActualizar,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        await solicitud_service.actualizar_datos(
            session, solicitud, datos.model_dump(exclude_unset=True)
        )
    except solicitud_service.SolicitudNoEditable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return await _solicitud_out(session, solicitud, con_lineas=True)


@solicitudes_router.patch("/{solicitud_id}/lineas", response_model=SolicitudOut)
async def actualizar_lineas_solicitud(
    solicitud_id: uuid.UUID,
    datos: LineasActualizar,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        await solicitud_service.actualizar_lineas(session, solicitud, datos.partida_ids)
    except (solicitud_service.SolicitudNoEditable, solicitud_service.SinPartidas) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return await _solicitud_out(session, solicitud, con_lineas=True)


@solicitudes_router.post("/{solicitud_id}/enviar", response_model=SolicitudConEnlaceOut)
async def enviar_solicitud(
    solicitud_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudConEnlaceOut:
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        enlace = await solicitud_service.enviar_solicitud(session, solicitud)
    except (
        solicitud_service.SolicitudYaEnviada,
        solicitud_service.SinCorreoDeProveedor,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except MailerError as exc:
        # La solicitud y el enlace ya existen y son válidos aunque el correo
        # falle — el usuario puede reintentarlo desde el mismo borrador.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo enviar el correo: {exc}",
        ) from exc
    await session.commit()
    base = await _solicitud_out(session, solicitud, con_lineas=True)
    return SolicitudConEnlaceOut(**base.model_dump(), enlace=enlace)


@solicitudes_router.post("/{solicitud_id}/enlace", response_model=EnlaceOut)
async def generar_enlace(
    solicitud_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> EnlaceOut:
    """Enlace del proveedor para pasárselo por otro medio. Emite uno nuevo e
    invalida el anterior — el token solo se guarda hasheado, así que no se
    puede volver a enseñar el que ya se mandó."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        enlace = await solicitud_service.generar_enlace(session, solicitud)
    except solicitud_service.SolicitudNoEditable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return EnlaceOut(enlace=enlace)


@solicitudes_router.delete("/{solicitud_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_solicitud(
    solicitud_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        await solicitud_service.eliminar_borrador(session, solicitud)
    except solicitud_service.SolicitudNoEditable as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()


@solicitudes_router.get("/por-presupuesto/{presupuesto_id}", response_model=list[SolicitudOut])
async def listar_por_presupuesto(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[SolicitudOut]:
    """Todas las solicitudes hechas sobre este presupuesto (borradores
    incluidos), con sus líneas — lo que alimenta la pestaña Comparativo."""
    filas = await solicitud_service.listar_por_presupuesto(session, presupuesto_id)
    return [
        await _solicitud_out(session, solicitud, con_lineas=True, proveedor=proveedor)
        for solicitud, proveedor in filas
    ]


class AprobarLineaOut(BaseModel):
    partida_id: uuid.UUID
    precio: Decimal


@solicitudes_router.post(
    "/{solicitud_id}/lineas/{linea_id}/aprobar", response_model=AprobarLineaOut
)
async def aprobar_linea(
    solicitud_id: uuid.UUID,
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> dict:
    """Elige la oferta de esta línea para la partida original: sustituye su
    descompuesto por la subcontrata de este proveedor, a su precio."""
    solicitud = await solicitud_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")
    linea = await solicitud_service.obtener_linea(session, linea_id)
    if linea is None or linea.solicitud_id != solicitud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")

    try:
        partida = await oferta_service.aprobar_linea(session, linea, solicitud)
    except (
        oferta_service.LineaSinPrecio,
        oferta_service.LineaYaAprobada,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await session.commit()
    return AprobarLineaOut(partida_id=partida.id, precio=partida.precio)


router = APIRouter()
router.include_router(albaranes_router)
router.include_router(lineas_router)
router.include_router(costes_router)
router.include_router(solicitudes_router)

# Espacio SIN autenticar (separata del proveedor). Va sin las guardas de
# arriba a propósito: quien entra no tiene cuenta. Se autoriza contra el token
# de su enlace en `publico_acceso.acceso_proveedor`, y `app.main` comprueba al
# arrancar que no cuelga de ahí ninguna ruta no declarada.
router.include_router(publico_router)
