"""Rutas de pedidos a proveedor. Aparte de `router.py`, mismo motivo que
`factura_recibida_router.py`: no seguir engordándolo."""

import uuid
from decimal import Decimal

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
    PedidoCreate,
    PedidoDetalle,
    PedidoLineaCreate,
    PedidoLineaOut,
    PedidoLineaUpdate,
    PedidoOut,
    PedidoResumen,
    PedidoUpdate,
)
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut

guard = Depends(require_module("compras"))

pedidos_router = APIRouter(prefix="/api/pedidos", tags=["compras"], dependencies=[guard])
pedido_lineas_router = APIRouter(
    prefix="/api/pedidos-lineas", tags=["compras"], dependencies=[guard]
)


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
    totales = await service.totales_de(session, [p.id for p, _ in filas])
    items = [
        PedidoResumen(
            **PedidoOut.model_validate(pedido).model_dump(),
            tercero_razon_social=razon_social,
            total=totales.get(pedido.id, Decimal("0.00")),
        )
        for pedido, razon_social in filas
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


def _detalle_de(pedido: Pedido, razon_social: str) -> PedidoDetalle:
    return PedidoDetalle(
        **PedidoOut.model_validate(pedido).model_dump(),
        tercero_razon_social=razon_social,
        lineas=[PedidoLineaOut.model_validate(l) for l in pedido.lineas],
        total=service.total_de(pedido.lineas),
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
    return _detalle_de(*resultado)


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
    return _detalle_de(pedido, razon_social)


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


@pedidos_router.post(
    "/{pedido_id}/lineas", response_model=PedidoLineaOut, status_code=status.HTTP_201_CREATED
)
async def anadir_linea(
    pedido_id: uuid.UUID,
    datos: PedidoLineaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoLineaOut:
    await _pedido_propio(session, pedido_id, alcance, principal)
    try:
        linea = await service.anadir_linea(session, pedido_id, datos)
    except service.LineaSinDatos as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert linea is not None
    return PedidoLineaOut.model_validate(linea)


async def _linea_propia(
    session: AsyncSession, linea_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    linea = await service.obtener_linea(session, linea_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    pedido = await service.obtener_obj(session, linea.pedido_id)
    assert pedido is not None
    verificar_propiedad(alcance, principal, pedido.creado_por_subject)
    return linea


@pedido_lineas_router.patch("/{linea_id}", response_model=PedidoLineaOut)
async def actualizar_linea(
    linea_id: uuid.UUID,
    datos: PedidoLineaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> PedidoLineaOut:
    await _linea_propia(session, linea_id, alcance, principal)
    linea = await service.actualizar_linea(session, linea_id, datos)
    assert linea is not None
    return PedidoLineaOut.model_validate(linea)


@pedido_lineas_router.delete("/{linea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_linea(
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _linea_propia(session, linea_id, alcance, principal)
    await service.eliminar_linea(session, linea_id)


router = APIRouter()
router.include_router(pedidos_router)
router.include_router(pedido_lineas_router)
