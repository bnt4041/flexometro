"""Pedidos a proveedor: la orden de compra en firme.

Dos vías para llegar a uno (ver plan "Pedido, Contrato y trazabilidad
documental"): confirmando la oferta ganadora de una `SolicitudPrecios` ya
resuelta (`origen_oferta_presupuesto_id`, líneas copiadas de esa oferta) o
directo a un proveedor conocido, sin RFQ de por medio (líneas a mano, igual
que un `Albaran`)."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.numeracion import siguiente_referencia_libre
from app.core.redondeo import redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.compras.models import Pedido, PedidoLinea
from app.modules.compras.pedido_schemas import (
    PedidoCreate,
    PedidoLineaCreate,
    PedidoLineaUpdate,
    PedidoUpdate,
)

TIPO_DOCUMENTO = "pedido"


class CodigoDuplicado(Exception):
    pass


class OrigenInvalido(Exception):
    pass


class LineaSinDatos(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    org_id = require_organization_id()

    async def existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(Pedido.id).where(
                    Pedido.organization_id == org_id, Pedido.codigo == codigo
                )
            )
        ) is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento=TIPO_DOCUMENTO, existe=existe
    )


async def _datos_linea(
    session: AsyncSession, datos: PedidoLineaCreate
) -> tuple[str, str, Decimal]:
    """Mismo criterio que `service._datos_linea` para `AlbaranLinea`: con
    concepto del banco de precios, resuelve descripción/unidad/precio de
    referencia; sin él, exige que vengan a mano."""
    if datos.concepto_id is not None:
        from app.modules.presupuestos.calculo import precio_referencia
        from app.modules.presupuestos.models import Concepto

        org_id = require_organization_id()
        concepto = await session.scalar(
            select(Concepto).where(
                Concepto.id == datos.concepto_id, Concepto.organization_id == org_id
            )
        )
        if concepto is None:
            raise LineaSinDatos("El concepto no existe en esta organización")

        precio = datos.precio_unitario
        if precio is None:
            precio = await precio_referencia(session, datos.concepto_id)
        if precio is None:
            raise LineaSinDatos(
                f"'{concepto.resumen}' no tiene tarifa de proveedor ni precio manual"
            )
        return (
            datos.descripcion or concepto.resumen,
            datos.unidad or concepto.unidad,
            precio,
        )

    if not datos.descripcion or datos.precio_unitario is None:
        raise LineaSinDatos(
            "Sin concepto del banco de precios hacen falta descripción y precio a mano"
        )
    return datos.descripcion, datos.unidad or "ud", datos.precio_unitario


def _nueva_linea(
    org_id: uuid.UUID,
    pedido_id: uuid.UUID,
    datos: PedidoLineaCreate,
    descripcion: str,
    unidad: str,
    precio: Decimal,
) -> PedidoLinea:
    return PedidoLinea(
        organization_id=org_id,
        pedido_id=pedido_id,
        concepto_id=datos.concepto_id,
        descripcion=descripcion,
        unidad=unidad,
        cantidad=datos.cantidad,
        precio_unitario=precio,
        importe=redondear_precio(datos.cantidad * precio),
        orden=datos.orden,
    )


async def _lineas_desde_oferta(
    session: AsyncSession, oferta_presupuesto_id: uuid.UUID
) -> list[PedidoLineaCreate]:
    """Copia las partidas de la oferta ganadora (un presupuesto tipo
    proveedor) como líneas alzadas del pedido — omite las que no tengan
    medición ni precio en vez de proponer una línea vacía."""
    from app.modules.presupuestos.models_presupuesto import Partida

    org_id = require_organization_id()
    partidas = (
        await session.execute(
            select(Partida).where(
                Partida.presupuesto_id == oferta_presupuesto_id,
                Partida.organization_id == org_id,
            )
        )
    ).scalars().all()
    return [
        PedidoLineaCreate(
            descripcion=p.resumen,
            unidad=p.unidad,
            cantidad=p.medicion,
            precio_unitario=p.precio,
            orden=orden,
        )
        for orden, p in enumerate(partidas)
        if p.medicion > 0 and p.precio > 0
    ]


async def crear(session: AsyncSession, datos: PedidoCreate) -> Pedido:
    from app.modules.compras.models import SolicitudPrecios
    from app.modules.compras.service import _validar_obra, _validar_proveedor

    org_id = require_organization_id()
    await _validar_obra(session, datos.obra_id)
    await _validar_proveedor(session, datos.proveedor_id)

    if datos.origen_solicitud_id is not None:
        existe_solicitud = await session.scalar(
            select(SolicitudPrecios.id).where(
                SolicitudPrecios.id == datos.origen_solicitud_id,
                SolicitudPrecios.organization_id == org_id,
            )
        )
        if existe_solicitud is None:
            raise OrigenInvalido("La solicitud de precios indicada no existe en esta organización")

    lineas = datos.lineas
    if not lineas and datos.origen_oferta_presupuesto_id is not None:
        lineas = await _lineas_desde_oferta(session, datos.origen_oferta_presupuesto_id)

    async def _existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(Pedido.id).where(
                    Pedido.organization_id == org_id, Pedido.codigo == codigo
                )
            )
        ) is not None

    if datos.codigo:
        if await _existe(datos.codigo):
            raise CodigoDuplicado(f"Ya existe un pedido con el código '{datos.codigo}'")
        codigo = datos.codigo
    else:
        codigo = await siguiente_referencia_libre(
            session, organization_id=org_id, tipo_documento=TIPO_DOCUMENTO, existe=_existe
        )

    pedido = Pedido(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo", "lineas"}),
        **datos_autoria(),
    )
    session.add(pedido)
    await session.flush()

    for linea in lineas:
        descripcion, unidad, precio = await _datos_linea(session, linea)
        session.add(_nueva_linea(org_id, pedido.id, linea, descripcion, unidad, precio))
    await session.flush()
    return pedido


async def listar(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[tuple[Pedido, str]], int]:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    base = (
        select(Pedido, Tercero.razon_social)
        .join(Tercero, Tercero.id == Pedido.proveedor_id)
        .where(Pedido.organization_id == org_id)
    )
    if obra_id is not None:
        base = base.where(Pedido.obra_id == obra_id)
    if proveedor_id is not None:
        base = base.where(Pedido.proveedor_id == proveedor_id)
    if creado_por_subject is not None:
        base = base.where(Pedido.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(
            base.with_only_columns(Pedido.id).order_by(None).subquery()
        )
    )
    filas = await session.execute(base.order_by(Pedido.fecha.desc()).limit(limit).offset(offset))
    return list(filas.all()), int(total or 0)


async def obtener(session: AsyncSession, pedido_id: uuid.UUID) -> tuple[Pedido, str] | None:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    fila = (
        await session.execute(
            select(Pedido, Tercero.razon_social)
            .join(Tercero, Tercero.id == Pedido.proveedor_id)
            .options(selectinload(Pedido.lineas))
            .where(Pedido.id == pedido_id, Pedido.organization_id == org_id)
        )
    ).first()
    return tuple(fila) if fila else None


async def obtener_obj(session: AsyncSession, pedido_id: uuid.UUID) -> Pedido | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Pedido).where(Pedido.id == pedido_id, Pedido.organization_id == org_id)
    )


async def actualizar(
    session: AsyncSession, pedido_id: uuid.UUID, datos: PedidoUpdate
) -> Pedido | None:
    pedido = await obtener_obj(session, pedido_id)
    if pedido is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(pedido, campo, valor)
    await session.flush()
    return pedido


async def eliminar(session: AsyncSession, pedido_id: uuid.UUID) -> bool:
    pedido = await obtener_obj(session, pedido_id)
    if pedido is None:
        return False
    await session.delete(pedido)
    await session.flush()
    return True


async def anadir_linea(
    session: AsyncSession, pedido_id: uuid.UUID, datos: PedidoLineaCreate
) -> PedidoLinea | None:
    org_id = require_organization_id()
    pedido = await obtener_obj(session, pedido_id)
    if pedido is None:
        return None
    descripcion, unidad, precio = await _datos_linea(session, datos)
    linea = _nueva_linea(org_id, pedido_id, datos, descripcion, unidad, precio)
    session.add(linea)
    await session.flush()
    return linea


async def obtener_linea(session: AsyncSession, linea_id: uuid.UUID) -> PedidoLinea | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(PedidoLinea).where(
            PedidoLinea.id == linea_id, PedidoLinea.organization_id == org_id
        )
    )


async def actualizar_linea(
    session: AsyncSession, linea_id: uuid.UUID, datos: PedidoLineaUpdate
) -> PedidoLinea | None:
    linea = await obtener_linea(session, linea_id)
    if linea is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(linea, campo, valor)
    if {"cantidad", "precio_unitario"} & cambios.keys():
        linea.importe = redondear_precio(linea.cantidad * linea.precio_unitario)
    await session.flush()
    return linea


async def eliminar_linea(session: AsyncSession, linea_id: uuid.UUID) -> bool:
    linea = await obtener_linea(session, linea_id)
    if linea is None:
        return False
    await session.delete(linea)
    await session.flush()
    return True


def total_de(lineas: list[PedidoLinea]) -> Decimal:
    return redondear_precio(sum((l.importe for l in lineas), Decimal("0.00")))


async def totales_de(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Total de cada pedido en una sola consulta agregada, para pintar un
    listado sin una consulta de líneas por fila — mismo patrón que
    `service.totales_de_albaranes`."""
    if not ids:
        return {}
    org_id = require_organization_id()
    filas = await session.execute(
        select(PedidoLinea.pedido_id, func.sum(PedidoLinea.importe))
        .where(PedidoLinea.pedido_id.in_(ids), PedidoLinea.organization_id == org_id)
        .group_by(PedidoLinea.pedido_id)
    )
    return {pedido_id: redondear_precio(total) for pedido_id, total in filas.all()}
