"""Rutas de pedidos a proveedor. Aparte de `router.py`, mismo motivo que
`factura_recibida_router.py`: no seguir engordándolo."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.compras import pedido_service as service
from app.modules.compras import service as compras_service
from app.modules.compras.models import Pedido, TipoPedido
from app.modules.compras.pedido_schemas import (
    PedidoCambioNaturalezaComponente,
    PedidoCambioPrecioComponente,
    PedidoCambioRendimientoComponente,
    PedidoCambioResumenComponente,
    PedidoCambioUnidadComponente,
    PedidoCapituloConPartidas,
    PedidoCapituloCreate,
    PedidoCapituloOut,
    PedidoCapituloUpdate,
    PedidoComponenteNuevo,
    PedidoCreate,
    PedidoDescomposicionOut,
    PedidoDetalle,
    PedidoLineaDescomposicionOut,
    PedidoMedicionCreate,
    PedidoMedicionOut,
    PedidoMedicionUpdate,
    PedidoOut,
    PedidoPartidaCreate,
    PedidoPartidaDetalle,
    PedidoPartidaOut,
    PedidoPartidaUpdate,
    PedidoPegarCapitulos,
    PedidoPegarComponentesDescompuesto,
    PedidoPegarMediciones,
    PedidoPegarPartidas,
    PedidoResultadoCambioPrecio,
    PedidoResultadoPegado,
    PedidoResumen,
    PedidoUpdate,
)
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut

guard = Depends(require_module("compras"))

pedidos_router = APIRouter(prefix="/api/pedidos", tags=["compras"], dependencies=[guard])


@pedidos_router.get("", response_model=Page[PedidoResumen])
async def listar(
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    tipo: TipoPedido | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> Page[PedidoResumen]:
    filas, total = await service.listar(
        session,
        obra_id=obra_id,
        proveedor_id=proveedor_id,
        tipo=tipo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    items = [
        PedidoResumen(
            **PedidoOut.model_validate(pedido).model_dump(),
            tercero_razon_social=razon_social,
            total=await service.total_de(session, pedido),
        )
        for pedido, razon_social in filas
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


async def _detalle_de(
    session: AsyncSession, pedido: Pedido, razon_social: str
) -> PedidoDetalle:
    return PedidoDetalle(
        **PedidoOut.model_validate(pedido).model_dump(),
        tercero_razon_social=razon_social,
        total=await service.total_de(session, pedido),
    )


@pedidos_router.post("", response_model=PedidoDetalle, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: PedidoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDetalle:
    try:
        pedido = await service.crear(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        service.OrigenInvalido,
        service.LineaSinDatos,
        compras_service.ObraInvalida,
        compras_service.ProveedorInvalido,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    resultado = await service.obtener(session, pedido.id)
    assert resultado is not None
    return await _detalle_de(session, *resultado)


async def _pedido_propio(
    session: AsyncSession, pedido_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    resultado = await service.obtener(session, pedido_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
    pedido, razon_social = resultado
    verificar_propiedad(alcance, principal, pedido.creado_por_subject)
    return pedido, razon_social


@pedidos_router.get("/{pedido_id}", response_model=PedidoDetalle)
async def detalle(
    pedido_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> PedidoDetalle:
    pedido, razon_social = await _pedido_propio(session, pedido_id, alcance, principal)
    return await _detalle_de(session, pedido, razon_social)


@pedidos_router.patch("/{pedido_id}", response_model=PedidoOut)
async def actualizar(
    pedido_id: uuid.UUID,
    datos: PedidoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoOut:
    await _pedido_propio(session, pedido_id, alcance, principal)
    pedido = await service.actualizar(session, pedido_id, datos)
    assert pedido is not None
    return PedidoOut.model_validate(pedido)


@pedidos_router.delete("/{pedido_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    pedido_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _pedido_propio(session, pedido_id, alcance, principal)
    await service.eliminar(session, pedido_id)


@pedidos_router.get("/{pedido_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    pedido_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[RegistroAuditoriaOut]:
    await _pedido_propio(session, pedido_id, alcance, principal)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Pedido), registro_id=pedido_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


# --- Capítulos, partidas, mediciones y descompuesto (Fase 2) ---
#
# Calcado del bloque de capítulos/partidas/mediciones/descomposición de
# `presupuesto_router.py`, con el mismo patrón de propiedad
# (`_capitulo_propio`/`_partida_propia`/`_medicion_propia`) y de "responder
# con el estado ya recalculado en la misma transacción, luego `commit()`":
# `get_session` confirma la transacción DESPUÉS de que FastAPI envía la
# respuesta, así que un cliente que encadene otra petición justo detrás
# (recargar el pedido al recibir un 204, por ejemplo) puede llegar antes de
# que el cambio esté confirmado si no se hace `commit()` aquí mismo.

pedidos_capitulos_router = APIRouter(
    prefix="/api/pedidos-capitulos", tags=["compras"], dependencies=[guard]
)
pedidos_partidas_router = APIRouter(
    prefix="/api/pedidos-partidas", tags=["compras"], dependencies=[guard]
)
pedidos_mediciones_router = APIRouter(
    prefix="/api/pedidos-mediciones", tags=["compras"], dependencies=[guard]
)


@pedidos_router.get("/{pedido_id}/capitulos", response_model=list[PedidoCapituloConPartidas])
async def listar_capitulos(
    pedido_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[PedidoCapituloConPartidas]:
    """El árbol completo del pedido —capítulos, partidas, mediciones y, si
    aplica, descomposición— para pintar la ficha de una sola vez."""
    await _pedido_propio(session, pedido_id, alcance, principal)
    capitulos = await service.cargar_capitulos(session, pedido_id)
    resultado = []
    for capitulo in capitulos:
        partidas = [await _partida_detalle_de(session, partida) for partida in capitulo.partidas]
        resultado.append(
            PedidoCapituloConPartidas(**PedidoCapituloOut.model_validate(capitulo).model_dump(), partidas=partidas)
        )
    return resultado


@pedidos_router.post(
    "/{pedido_id}/capitulos", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def crear_capitulo(
    pedido_id: uuid.UUID,
    datos: PedidoCapituloCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> dict:
    await _pedido_propio(session, pedido_id, alcance, principal)
    capitulo = await service.crear_capitulo(session, pedido_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@pedidos_router.post("/{pedido_id}/capitulos/pegar", response_model=PedidoResultadoPegado)
async def pegar_capitulos(
    pedido_id: uuid.UUID,
    datos: PedidoPegarCapitulos,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoResultadoPegado:
    """Copia o mueve capítulos enteros —con sus partidas, descompuesto y
    mediciones— a este pedido (Fase 5: portapapeles, del mismo pedido o de
    otro)."""
    await _pedido_propio(session, pedido_id, alcance, principal)
    pegados = await service.pegar_capitulos(session, pedido_id, datos.capitulo_ids, datos.alcance)
    await session.commit()
    return PedidoResultadoPegado(pegadas=pegados)


async def _capitulo_propio(
    session: AsyncSession, capitulo_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    capitulo = await service.obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    await _pedido_propio(session, capitulo.pedido_id, alcance, principal)
    return capitulo


@pedidos_capitulos_router.patch("/{capitulo_id}", response_model=dict)
async def actualizar_capitulo(
    capitulo_id: uuid.UUID,
    datos: PedidoCapituloUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> dict:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    capitulo = await service.actualizar_capitulo(session, capitulo_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@pedidos_capitulos_router.delete("/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    await service.eliminar_capitulo(session, capitulo_id)
    await session.commit()


@pedidos_capitulos_router.post(
    "/{capitulo_id}/partidas", response_model=PedidoPartidaDetalle, status_code=status.HTTP_201_CREATED
)
async def crear_partida(
    capitulo_id: uuid.UUID,
    datos: PedidoPartidaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoPartidaDetalle:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    try:
        partida = await service.crear_partida(session, capitulo_id, datos)
    except service.ConceptoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except service.PartidaSinDatos as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert partida is not None
    await session.commit()
    return await _partida_detalle_de(session, partida)


@pedidos_capitulos_router.post("/{capitulo_id}/partidas/pegar", response_model=PedidoResultadoPegado)
async def pegar_partidas(
    capitulo_id: uuid.UUID,
    datos: PedidoPegarPartidas,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoResultadoPegado:
    """Copia o mueve partidas enteras —con su descompuesto y sus
    mediciones— a este capítulo (Fase 5: portapapeles, del mismo pedido o de
    otro)."""
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    pegadas = await service.pegar_partidas(session, capitulo_id, datos.partida_ids, datos.alcance)
    await session.commit()
    return PedidoResultadoPegado(pegadas=pegadas)


async def _partida_propia(
    session: AsyncSession, partida_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    partida = await service.obtener_partida(session, partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    await _pedido_propio(session, partida.pedido_id, alcance, principal)
    return partida


async def _partida_detalle_de(session: AsyncSession, partida) -> PedidoPartidaDetalle:
    # `tiene_desglose`/`descomposicion_propia` no son columnas: se calculan
    # aquí a partir de las relaciones ya cargadas (`obtener_partida` las trae
    # con `selectinload`), mismo criterio que `pedido_service.cargar_capitulos`.
    partida.tiene_desglose = len(partida.mediciones) > 0
    partida.descomposicion_propia = len(partida.descomposicion) > 0
    detalle = PedidoPartidaDetalle(
        **PedidoPartidaOut.model_validate(partida).model_dump(),
        mediciones=[PedidoMedicionOut.model_validate(m) for m in partida.mediciones],
    )
    # Se informa el precio del cuadro solo cuando difiere (mismo criterio que
    # `presupuesto_router.detalle_partida`): es la señal de que el pedido
    # sigue diciendo un precio distinto del que ahora tiene el concepto.
    if partida.concepto_id is not None:
        from app.modules.presupuestos.service import obtener_concepto

        concepto = await obtener_concepto(session, partida.concepto_id)
        if concepto is not None and concepto.precio != partida.precio:
            detalle.precio_cuadro = concepto.precio
    return detalle


@pedidos_partidas_router.get("/{partida_id}", response_model=PedidoPartidaDetalle)
async def detalle_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> PedidoPartidaDetalle:
    partida = await _partida_propia(session, partida_id, alcance, principal)
    return await _partida_detalle_de(session, partida)


@pedidos_partidas_router.patch("/{partida_id}", response_model=PedidoPartidaOut)
async def actualizar_partida(
    partida_id: uuid.UUID,
    datos: PedidoPartidaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoPartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    partida = await service.actualizar_partida(session, partida_id, datos)
    assert partida is not None
    await session.commit()
    return PedidoPartidaOut.model_validate(partida)


@pedidos_partidas_router.delete("/{partida_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _partida_propia(session, partida_id, alcance, principal)
    await service.eliminar_partida(session, partida_id)
    await session.commit()


def _traducir_no_disponible(exc: service.DescomposicionNoDisponible) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@pedidos_partidas_router.get("/{partida_id}/descomposicion", response_model=PedidoDescomposicionOut)
async def descomposicion_de_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> PedidoDescomposicionOut:
    """Descompuesto de la partida — solo disponible en pedidos de cliente
    (409 en pedidos de proveedor, ver `DescomposicionNoDisponible`)."""
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        resultado = await service.descomposicion_de_partida(session, partida_id)
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    propia, lineas = resultado
    return PedidoDescomposicionOut(
        propia=propia, lineas=[PedidoLineaDescomposicionOut(**linea) for linea in lineas]
    )


async def _descomposicion_fresca(session: AsyncSession, partida_id: uuid.UUID) -> PedidoDescomposicionOut:
    resultado = await service.descomposicion_de_partida(session, partida_id)
    lineas = [] if resultado is None else resultado[1]
    return PedidoDescomposicionOut(
        propia=bool(resultado and resultado[0]),
        lineas=[PedidoLineaDescomposicionOut(**linea) for linea in lineas],
    )


@pedidos_partidas_router.post(
    "/{partida_id}/descomposicion",
    response_model=PedidoDescomposicionOut,
    status_code=status.HTTP_201_CREATED,
)
async def anadir_componente(
    partida_id: uuid.UUID,
    datos: PedidoComponenteNuevo,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        creado = await service.anadir_componente(
            session, partida_id, datos.hijo_id, datos.rendimiento, datos.factor
        )
    except service.ConceptoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if not creado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.post(
    "/{partida_id}/descomposicion/independizar", response_model=PedidoDescomposicionOut
)
async def independizar_descomposicion_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    partida = await _partida_propia(session, partida_id, alcance, principal)
    try:
        await service.independizar_descomposicion(session, partida)
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.delete(
    "/{partida_id}/descomposicion/{linea_id}", response_model=PedidoDescomposicionOut
)
async def quitar_componente(
    partida_id: uuid.UUID,
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        quitado = await service.quitar_componente(session, partida_id, linea_id)
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if not quitado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.patch(
    "/{partida_id}/descomposicion/precio", response_model=PedidoResultadoCambioPrecio
)
async def cambiar_precio_componente(
    partida_id: uuid.UUID,
    datos: PedidoCambioPrecioComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoResultadoCambioPrecio:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        afectadas = await service.cambiar_precio_componente(
            session, partida_id, datos.hijo_id, datos.precio, datos.alcance
        )
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    salida = await _descomposicion_fresca(session, partida_id)
    # Igual que en `presupuesto_router.cambiar_precio_componente`: se confirma
    # aquí para que cualquier lectura que dispare el cliente al recibir la
    # respuesta ya vea el cambio.
    await session.commit()
    return PedidoResultadoCambioPrecio(partidas_afectadas=afectadas, descomposicion=salida)


@pedidos_partidas_router.patch(
    "/{partida_id}/descomposicion/rendimiento", response_model=PedidoDescomposicionOut
)
async def cambiar_rendimiento_componente(
    partida_id: uuid.UUID,
    datos: PedidoCambioRendimientoComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        tocado = await service.cambiar_rendimiento_componente(
            session, partida_id, datos.hijo_id, datos.rendimiento
        )
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if not tocado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.patch(
    "/{partida_id}/descomposicion/resumen", response_model=PedidoDescomposicionOut
)
async def cambiar_resumen_componente(
    partida_id: uuid.UUID,
    datos: PedidoCambioResumenComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        tocado = await service.cambiar_resumen_componente(
            session, partida_id, datos.hijo_id, datos.resumen
        )
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if not tocado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.patch(
    "/{partida_id}/descomposicion/naturaleza", response_model=PedidoDescomposicionOut
)
async def cambiar_naturaleza_componente(
    partida_id: uuid.UUID,
    datos: PedidoCambioNaturalezaComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        tocado = await service.cambiar_naturaleza_componente(
            session, partida_id, datos.hijo_id, datos.naturaleza
        )
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if not tocado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.patch(
    "/{partida_id}/descomposicion/unidad", response_model=PedidoDescomposicionOut
)
async def cambiar_unidad_componente(
    partida_id: uuid.UUID,
    datos: PedidoCambioUnidadComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        tocado = await service.cambiar_unidad_componente(
            session, partida_id, datos.hijo_id, datos.unidad
        )
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    if not tocado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@pedidos_partidas_router.post("/{partida_id}/descomposicion/pegar", response_model=PedidoResultadoPegado)
async def pegar_componentes(
    partida_id: uuid.UUID,
    datos: PedidoPegarComponentesDescompuesto,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoResultadoPegado:
    """Copia o mueve componentes de un descompuesto a esta partida (Fase 5),
    independizándola del banco de precios si aún lo heredaba — solo
    disponible en pedidos de cliente (409 en pedidos de proveedor)."""
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        pegadas = await service.pegar_componentes_descompuesto(
            session, partida_id, datos.linea_ids, datos.alcance
        )
    except service.DescomposicionNoDisponible as exc:
        raise _traducir_no_disponible(exc) from exc
    await session.commit()
    return PedidoResultadoPegado(pegadas=pegadas)


@pedidos_partidas_router.post(
    "/{partida_id}/mediciones", response_model=PedidoMedicionOut, status_code=status.HTTP_201_CREATED
)
async def crear_medicion(
    partida_id: uuid.UUID,
    datos: PedidoMedicionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoMedicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    medicion = await service.crear_medicion(session, partida_id, datos)
    assert medicion is not None
    await session.commit()
    return PedidoMedicionOut.model_validate(medicion)


@pedidos_partidas_router.post("/{partida_id}/mediciones/pegar", response_model=PedidoResultadoPegado)
async def pegar_mediciones(
    partida_id: uuid.UUID,
    datos: PedidoPegarMediciones,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoResultadoPegado:
    """Copia o mueve mediciones sueltas a esta partida (Fase 5)."""
    await _partida_propia(session, partida_id, alcance, principal)
    pegadas = await service.pegar_mediciones(session, partida_id, datos.medicion_ids, datos.alcance)
    await session.commit()
    return PedidoResultadoPegado(pegadas=pegadas)


async def _medicion_propia(
    session: AsyncSession, medicion_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    medicion = await service.obtener_medicion(session, medicion_id)
    if medicion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medición no encontrada")
    await _partida_propia(session, medicion.partida_id, alcance, principal)
    return medicion


@pedidos_mediciones_router.patch("/{medicion_id}", response_model=PedidoMedicionOut)
async def actualizar_medicion(
    medicion_id: uuid.UUID,
    datos: PedidoMedicionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoMedicionOut:
    await _medicion_propia(session, medicion_id, alcance, principal)
    medicion = await service.actualizar_medicion(session, medicion_id, datos)
    assert medicion is not None
    await session.commit()
    return PedidoMedicionOut.model_validate(medicion)


@pedidos_mediciones_router.delete("/{medicion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_medicion(
    medicion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _medicion_propia(session, medicion_id, alcance, principal)
    await service.eliminar_medicion(session, medicion_id)
    await session.commit()


router = APIRouter()
router.include_router(pedidos_router)
router.include_router(pedidos_capitulos_router)
router.include_router(pedidos_partidas_router)
router.include_router(pedidos_mediciones_router)
