import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.mailer import MailerError
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.compras import costes, oferta_service, service, solicitud_service
from app.modules.compras.models import (
    Albaran,
    OfertaLinea,
    SolicitudDestinatario,
    SolicitudLinea,
    TipoAlbaran,
)
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut
from app.modules.compras.factura_recibida_router import (
    router as facturas_recibidas_router,
    totales_router as compras_totales_router,
)
from app.modules.compras.factura_recibida_partidas_router import (
    router as factura_recibida_partidas_router,
)
from app.modules.compras.pedido_ia_router import router as pedido_ia_router
from app.modules.compras.pedido_router import router as pedido_router
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
    DestinatarioActualizar,
    DestinatarioCrear,
    DestinatarioOut,
    EnlaceOut,
    LineasActualizar,
    OfertaLineaOut,
    SolicitudActualizar,
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
    tipo: TipoAlbaran | None = None,
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
        tipo=tipo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    totales = await service.totales_de_albaranes(session, [a.id for a, _ in filas])
    items = [
        AlbaranResumen(
            **AlbaranOut.model_validate(albaran).model_dump(),
            tercero_razon_social=razon_social,
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
        service.PedidoInvalido,
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
        tercero_razon_social=razon_social,
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
        tercero_razon_social=razon_social,
        lineas=[AlbaranLineaOut.model_validate(l) for l in albaran.lineas],
        total=service.total_de(albaran.lineas),
    )


@albaranes_router.get("/{albaran_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    albaran_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[RegistroAuditoriaOut]:
    await _albaran_propio(session, albaran_id, alcance, principal)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Albaran), registro_id=albaran_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@albaranes_router.patch("/{albaran_id}", response_model=AlbaranOut)
async def actualizar(
    albaran_id: uuid.UUID,
    datos: AlbaranUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranOut:
    await _albaran_propio(session, albaran_id, alcance, principal)
    try:
        albaran = await service.actualizar_albaran(session, albaran_id, datos)
    except service.PedidoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
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


async def _solicitud_out(session: AsyncSession, solicitud) -> SolicitudOut:
    """El paquete entero de una sola lectura: sus líneas y, por cada
    destinatario, lo que lleva ofertado. Es el formato que la matriz del
    comparativo necesita para pintarse sin ir pidiendo cosas."""
    lineas = [
        SolicitudLineaOut.model_validate(l)
        for l in (
            await session.execute(
                select(SolicitudLinea)
                .where(SolicitudLinea.solicitud_id == solicitud.id)
                .order_by(SolicitudLinea.orden)
            )
        ).scalars()
    ]

    filas = (
        await session.execute(
            select(SolicitudDestinatario, Tercero)
            .join(Tercero, Tercero.id == SolicitudDestinatario.proveedor_id)
            .where(SolicitudDestinatario.solicitud_id == solicitud.id)
            .order_by(SolicitudDestinatario.created_at)
        )
    ).all()

    destinatarios = []
    for destinatario, proveedor in filas:
        ofertas = [
            OfertaLineaOut.model_validate(o)
            for o in (
                await session.execute(
                    select(OfertaLinea).where(
                        OfertaLinea.destinatario_id == destinatario.id
                    )
                )
            ).scalars()
        ]
        destinatarios.append(
            DestinatarioOut(
                id=destinatario.id,
                proveedor_id=destinatario.proveedor_id,
                proveedor_razon_social=proveedor.razon_social,
                proveedor_email=proveedor.email,
                email_destino=destinatario.email_destino,
                estado=destinatario.estado,
                enviada_en=destinatario.enviada_en,
                respondida_en=destinatario.respondida_en,
                oferta_presupuesto_id=destinatario.oferta_presupuesto_id,
                ofertas=ofertas,
            )
        )

    return SolicitudOut(
        id=solicitud.id,
        codigo=solicitud.codigo,
        titulo=solicitud.titulo,
        presupuesto_id=solicitud.presupuesto_id,
        estado=solicitud.estado,
        fecha_limite=solicitud.fecha_limite,
        notas=solicitud.notas,
        lineas=lineas,
        destinatarios=destinatarios,
    )


async def _solicitud_o_404(session: AsyncSession, solicitud_id: uuid.UUID):
    solicitud = await solicitud_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")
    return solicitud


async def _destinatario_o_404(
    session: AsyncSession, solicitud_id: uuid.UUID, destinatario_id: uuid.UUID
):
    destinatario = await solicitud_service.obtener_destinatario(session, destinatario_id)
    if destinatario is None or destinatario.solicitud_id != solicitud_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado en esta solicitud"
        )
    return destinatario


_ERRORES_422 = (
    solicitud_service.PresupuestoInvalido,
    solicitud_service.ProveedorInvalido,
    solicitud_service.SinPartidas,
    solicitud_service.DestinatarioNoEditable,
    solicitud_service.SinCorreoDeProveedor,
)


@solicitudes_router.post("", response_model=SolicitudOut, status_code=status.HTTP_201_CREATED)
async def crear_solicitud(
    datos: SolicitudCrear,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    """Deja el paquete en borrador — no manda nada todavía. Se completa y se
    envía proveedor a proveedor desde su ficha en la pestaña Comparativo."""
    try:
        solicitud = await solicitud_service.crear_solicitud(
            session,
            presupuesto_id=datos.presupuesto_id,
            titulo=datos.titulo,
            proveedor_ids=datos.proveedor_ids,
            partida_ids=datos.partida_ids,
            componentes=[(c.partida_id, c.concepto_id) for c in datos.componentes],
            fecha_limite=datos.fecha_limite,
            notas=datos.notas,
        )
    except _ERRORES_422 as exc:
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
    await solicitud_service.actualizar_datos(
        session, solicitud, datos.model_dump(exclude_unset=True)
    )
    await session.commit()
    return await _solicitud_out(session, solicitud)


@solicitudes_router.patch("/{solicitud_id}/lineas", response_model=SolicitudOut)
async def actualizar_lineas_solicitud(
    solicitud_id: uuid.UUID,
    datos: LineasActualizar,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    """Editable siempre, también con el paquete ya enviado: quien lo manda
    decide si reenvía a los proveedores anteriores."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        await solicitud_service.actualizar_lineas(
            session,
            solicitud,
            datos.partida_ids,
            componentes=[(c.partida_id, c.concepto_id) for c in datos.componentes],
        )
    except _ERRORES_422 as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return await _solicitud_out(session, solicitud)


@solicitudes_router.delete("/{solicitud_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_solicitud(
    solicitud_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    """Borra la solicitud en cualquier estado. Se lleva por cascada lo que
    hubieran ofertado los proveedores y sus enlaces; los presupuestos-oferta
    ya generados se conservan. Avisar de eso es cosa de la pantalla."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    await solicitud_service.eliminar(session, solicitud)
    await session.commit()


# --- Destinatarios: a quién se le pide ---


@solicitudes_router.post("/{solicitud_id}/destinatarios", response_model=SolicitudOut)
async def anadir_destinatario(
    solicitud_id: uuid.UUID,
    datos: DestinatarioCrear,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    """Un proveedor más al paquete, también si ya se envió a otros: recibe
    exactamente las mismas líneas."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    try:
        await solicitud_service.anadir_destinatario(
            session, solicitud, datos.proveedor_id, datos.email_destino
        )
    except _ERRORES_422 as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return await _solicitud_out(session, solicitud)


@solicitudes_router.patch(
    "/{solicitud_id}/destinatarios/{destinatario_id}", response_model=SolicitudOut
)
async def actualizar_destinatario(
    solicitud_id: uuid.UUID,
    destinatario_id: uuid.UUID,
    datos: DestinatarioActualizar,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    solicitud = await _solicitud_o_404(session, solicitud_id)
    destinatario = await _destinatario_o_404(session, solicitud_id, destinatario_id)
    destinatario.email_destino = datos.email_destino
    await session.commit()
    return await _solicitud_out(session, solicitud)


@solicitudes_router.delete(
    "/{solicitud_id}/destinatarios/{destinatario_id}", response_model=SolicitudOut
)
async def quitar_destinatario(
    solicitud_id: uuid.UUID,
    destinatario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> SolicitudOut:
    """Saca al proveedor en cualquier estado. Se lleva su acceso y lo que
    hubiera ofertado, y deja sin adjudicar sus líneas; su presupuesto-oferta
    se conserva. Avisar de eso es cosa de la pantalla."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    destinatario = await _destinatario_o_404(session, solicitud_id, destinatario_id)
    await solicitud_service.quitar_destinatario(session, destinatario)
    await session.commit()
    return await _solicitud_out(session, solicitud)


@solicitudes_router.post(
    "/{solicitud_id}/destinatarios/{destinatario_id}/enviar", response_model=EnlaceOut
)
async def enviar_a_destinatario(
    solicitud_id: uuid.UUID,
    destinatario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> EnlaceOut:
    """Manda el paquete a este proveedor. Sirve igual para el primer envío y
    para reenviar tras retocar las líneas: emite un enlace nuevo, el anterior
    muere, y lo que ya hubiera rellenado se conserva."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    destinatario = await _destinatario_o_404(session, solicitud_id, destinatario_id)
    try:
        enlace = await solicitud_service.enviar_a(session, solicitud, destinatario)
    except _ERRORES_422 as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except MailerError as exc:
        # El enlace ya existe y es válido aunque el correo falle — se puede
        # reintentar o pasar el enlace a mano.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo enviar el correo: {exc}",
        ) from exc
    await session.commit()
    return EnlaceOut(enlace=enlace)


@solicitudes_router.post(
    "/{solicitud_id}/destinatarios/{destinatario_id}/enlace", response_model=EnlaceOut
)
async def generar_enlace(
    solicitud_id: uuid.UUID,
    destinatario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> EnlaceOut:
    """Enlace de este proveedor para pasárselo por otro medio. Emite uno nuevo
    e invalida el anterior — el token solo se guarda hasheado, así que no se
    puede volver a enseñar el que ya se mandó."""
    solicitud = await _solicitud_o_404(session, solicitud_id)
    destinatario = await _destinatario_o_404(session, solicitud_id, destinatario_id)
    try:
        enlace = await solicitud_service.generar_enlace(session, solicitud, destinatario)
    except _ERRORES_422 as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return EnlaceOut(enlace=enlace)


@solicitudes_router.get("/por-obra/{obra_id}", response_model=list[SolicitudOut])
async def listar_por_obra(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[SolicitudOut]:
    """El comparativo de la obra: los paquetes de precios de todos los
    presupuestos que ejecuta, principal y anexos.

    Es lo mismo que ve la pestaña Comparativo del presupuesto, pero reunido por
    obra — que es donde de verdad se usa: saber a quién se adjudicó cada
    partida es el punto de partida de las compras.
    """
    from app.modules.obras.service import obtener_obra

    if await obtener_obra(session, obra_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    solicitudes = await solicitud_service.listar_por_obra(session, obra_id)
    return [await _solicitud_out(session, s) for s in solicitudes]


@solicitudes_router.get("/por-presupuesto/{presupuesto_id}", response_model=list[SolicitudOut])
async def listar_por_presupuesto(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[SolicitudOut]:
    """Todos los paquetes de este presupuesto (borradores incluidos) — lo que
    alimenta la pestaña Comparativo."""
    solicitudes = await solicitud_service.listar_por_presupuesto(session, presupuesto_id)
    return [await _solicitud_out(session, s) for s in solicitudes]


class AprobarLineaOut(BaseModel):
    partida_id: uuid.UUID
    precio: Decimal


@solicitudes_router.post("/ofertas-linea/{oferta_id}/aprobar", response_model=AprobarLineaOut)
async def aprobar_linea(
    oferta_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AprobarLineaOut:
    """Adjudica una línea a un proveedor: aplica su precio sobre la partida
    original del presupuesto (sustituyendo su descompuesto por la subcontrata,
    o cambiando el precio del componente si lo que se pidió era un componente)."""
    oferta = await solicitud_service.obtener_oferta_linea(session, oferta_id)
    if oferta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oferta no encontrada")
    linea = await solicitud_service.obtener_linea(session, oferta.linea_id)
    destinatario = await solicitud_service.obtener_destinatario(session, oferta.destinatario_id)
    if linea is None or destinatario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Oferta no encontrada")
    solicitud = await solicitud_service.obtener_solicitud(session, linea.solicitud_id)
    if solicitud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud no encontrada")

    try:
        partida = await oferta_service.aprobar_linea(
            session, oferta, linea, destinatario, solicitud
        )
    except (oferta_service.LineaSinPrecio, oferta_service.LineaYaAprobada) as exc:
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
# Facturas de proveedor y pedidos: van en su propio módulo, `router.py` ya
# es largo.
router.include_router(facturas_recibidas_router)
router.include_router(compras_totales_router)
# Capítulos/partidas/mediciones de la factura recibida (Fase 2): en su propio
# módulo para no seguir engordando `factura_recibida_router.py`.
router.include_router(factura_recibida_partidas_router)
router.include_router(pedido_router)
# "Ayuda con IA" sobre pedidos de cliente (Fase 4): aparte porque pide
# además el módulo `ia` activo, mismo motivo que `factura_recibida_partidas_
# router` está aparte de `factura_recibida_router`.
router.include_router(pedido_ia_router)

# Espacio SIN autenticar (separata del proveedor). Va sin las guardas de
# arriba a propósito: quien entra no tiene cuenta. Se autoriza contra el token
# de su enlace en `publico_acceso.acceso_proveedor`, y `app.main` comprueba al
# arrancar que no cuelga de ahí ninguna ruta no declarada.
router.include_router(publico_router)
