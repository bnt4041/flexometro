import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.numeracion import siguiente_referencia
from app.core.redondeo import redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.compras.models import Albaran, AlbaranLinea
from app.modules.compras.schemas import (
    AlbaranCreate,
    AlbaranLineaCreate,
    AlbaranLineaUpdate,
    AlbaranUpdate,
)


class CodigoDuplicado(Exception):
    pass


class ObraInvalida(Exception):
    pass


class ProveedorInvalido(Exception):
    pass


class ConceptoInvalido(Exception):
    pass


class LineaSinDatos(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    """Fase 16: patrón configurable por cuenta (Administración → ficha de
    cuenta → Numeración), en vez del prefijo "ALB" fijo de antes."""
    org_id = require_organization_id()
    return await siguiente_referencia(session, organization_id=org_id, tipo_documento="albaran")


async def _validar_obra(session: AsyncSession, obra_id: uuid.UUID) -> None:
    from app.modules.obras.service import obtener_obra

    if await obtener_obra(session, obra_id) is None:
        raise ObraInvalida("La obra no existe en esta organización")


async def _validar_proveedor(session: AsyncSession, proveedor_id: uuid.UUID) -> None:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    fila = await session.execute(
        select(Tercero.es_proveedor).where(
            Tercero.id == proveedor_id, Tercero.organization_id == org_id
        )
    )
    resultado = fila.first()
    if resultado is None:
        raise ProveedorInvalido("El proveedor indicado no existe en esta organización")
    if not resultado[0]:
        raise ProveedorInvalido("El tercero indicado no tiene el rol de proveedor")


async def _datos_linea(
    session: AsyncSession, datos: AlbaranLineaCreate
) -> tuple[str, str, Decimal]:
    """Resuelve descripción, unidad y precio de una línea a partir del
    concepto del banco de precios, si lo tiene; si no, exige que vengan a mano."""
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
            raise ConceptoInvalido("El concepto no existe en esta organización")

        precio = datos.precio_unitario
        if precio is None:
            precio = await precio_referencia(session, datos.concepto_id)
        if precio is None:
            raise ConceptoInvalido(
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


def _nueva_linea(org_id: uuid.UUID, albaran_id: uuid.UUID, datos: AlbaranLineaCreate, descripcion, unidad, precio) -> AlbaranLinea:
    return AlbaranLinea(
        organization_id=org_id,
        albaran_id=albaran_id,
        concepto_id=datos.concepto_id,
        capitulo_id=datos.capitulo_id,
        descripcion=descripcion,
        unidad=unidad,
        cantidad=datos.cantidad,
        precio_unitario=precio,
        importe=redondear_precio(datos.cantidad * precio),
        orden=datos.orden,
    )


async def crear_albaran(session: AsyncSession, datos: AlbaranCreate) -> Albaran:
    org_id = require_organization_id()
    await _validar_obra(session, datos.obra_id)
    await _validar_proveedor(session, datos.proveedor_id)

    codigo = datos.codigo or await siguiente_codigo(session)
    existe = await session.scalar(
        select(Albaran.id).where(Albaran.organization_id == org_id, Albaran.codigo == codigo)
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe un albarán con el código '{codigo}'")

    albaran = Albaran(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo", "lineas"}),
        **datos_autoria(),
    )
    session.add(albaran)
    await session.flush()

    for linea in datos.lineas:
        descripcion, unidad, precio = await _datos_linea(session, linea)
        session.add(_nueva_linea(org_id, albaran.id, linea, descripcion, unidad, precio))
    await session.flush()
    return albaran


async def listar_albaranes(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[tuple[Albaran, str]], int]:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    base = (
        select(Albaran, Tercero.razon_social)
        .join(Tercero, Tercero.id == Albaran.proveedor_id)
        .where(Albaran.organization_id == org_id)
    )
    if obra_id is not None:
        base = base.where(Albaran.obra_id == obra_id)
    if proveedor_id is not None:
        base = base.where(Albaran.proveedor_id == proveedor_id)
    if creado_por_subject is not None:
        base = base.where(Albaran.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(
            base.with_only_columns(Albaran.id).order_by(None).subquery()
        )
    )
    filas = await session.execute(base.order_by(Albaran.fecha.desc()).limit(limit).offset(offset))
    return list(filas.all()), int(total or 0)


async def obtener_albaran(
    session: AsyncSession, albaran_id: uuid.UUID
) -> tuple[Albaran, str] | None:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    fila = (
        await session.execute(
            select(Albaran, Tercero.razon_social)
            .join(Tercero, Tercero.id == Albaran.proveedor_id)
            .options(selectinload(Albaran.lineas))
            .where(Albaran.id == albaran_id, Albaran.organization_id == org_id)
        )
    ).first()
    return tuple(fila) if fila else None


async def obtener_albaran_obj(session: AsyncSession, albaran_id: uuid.UUID) -> Albaran | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Albaran).where(Albaran.id == albaran_id, Albaran.organization_id == org_id)
    )


async def actualizar_albaran(
    session: AsyncSession, albaran_id: uuid.UUID, datos: AlbaranUpdate
) -> Albaran | None:
    albaran = await obtener_albaran_obj(session, albaran_id)
    if albaran is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(albaran, campo, valor)
    await session.flush()
    return albaran


async def eliminar_albaran(session: AsyncSession, albaran_id: uuid.UUID) -> bool:
    albaran = await obtener_albaran_obj(session, albaran_id)
    if albaran is None:
        return False
    await session.delete(albaran)
    await session.flush()
    return True


async def anadir_linea(
    session: AsyncSession, albaran_id: uuid.UUID, datos: AlbaranLineaCreate
) -> AlbaranLinea | None:
    org_id = require_organization_id()
    albaran = await obtener_albaran_obj(session, albaran_id)
    if albaran is None:
        return None

    descripcion, unidad, precio = await _datos_linea(session, datos)
    linea = _nueva_linea(org_id, albaran_id, datos, descripcion, unidad, precio)
    session.add(linea)
    await session.flush()
    return linea


async def obtener_linea(session: AsyncSession, linea_id: uuid.UUID) -> AlbaranLinea | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(AlbaranLinea).where(
            AlbaranLinea.id == linea_id, AlbaranLinea.organization_id == org_id
        )
    )


async def actualizar_linea(
    session: AsyncSession, linea_id: uuid.UUID, datos: AlbaranLineaUpdate
) -> AlbaranLinea | None:
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


def total_de(lineas: list[AlbaranLinea]) -> Decimal:
    return redondear_precio(sum((l.importe for l in lineas), Decimal("0.00")))


async def totales_de_albaranes(
    session: AsyncSession, ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """Total de cada albarán en una sola consulta agregada, para no hacer una
    consulta de líneas por fila al construir un listado."""
    if not ids:
        return {}
    org_id = require_organization_id()
    filas = await session.execute(
        select(AlbaranLinea.albaran_id, func.sum(AlbaranLinea.importe))
        .where(AlbaranLinea.albaran_id.in_(ids), AlbaranLinea.organization_id == org_id)
        .group_by(AlbaranLinea.albaran_id)
    )
    return {albaran_id: redondear_precio(total) for albaran_id, total in filas.all()}


async def coste_materiales_por_capitulo(
    session: AsyncSession, obra_id: uuid.UUID
) -> dict[uuid.UUID | None, Decimal]:
    """Coste real de materiales de la obra, agrupado por capítulo.

    Lo consume el informe combinado (`costes.py`), en el mismo módulo.
    """
    org_id = require_organization_id()
    filas = await session.execute(
        select(AlbaranLinea.capitulo_id, func.sum(AlbaranLinea.importe))
        .join(Albaran, Albaran.id == AlbaranLinea.albaran_id)
        .where(Albaran.obra_id == obra_id, AlbaranLinea.organization_id == org_id)
        .group_by(AlbaranLinea.capitulo_id)
    )
    return {capitulo_id: importe for capitulo_id, importe in filas.all()}
