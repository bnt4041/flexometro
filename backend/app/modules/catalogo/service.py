"""Servicios del catálogo.

El acoplamiento con `terceros` se queda en la clave ajena y en una consulta
explícita: no hay relación ORM entre `PrecioSuministro` y `Tercero`, para que
la frontera entre módulos siga siendo visible en el código.

Producto/Familia/PrecioSuministro son maestros compartibles (Fase 15): los
listados y `obtener_producto_visible` (detalle de solo lectura) usan
`organizaciones_visibles()` — además de la propia organización, incluye las
hermanas de la misma cuenta cuando esta tiene `compartir_maestros` activo.
Las altas, ediciones y bajas, y cualquier función que VALIDA propiedad antes
de escribir (`_validar_proveedor`, alta de suministro...), siguen atadas
siempre a la organización propia — nunca se puede dar de alta una tarifa
bajo el producto de una organización hermana solo porque se pueda leer.
`precio_referencia` (alimenta el cálculo de precio básico) también se deja
deliberadamente estricto: que dos organizaciones vean el mismo producto no
implica que su cascada de precios dependa en silencio de la tarifa
negociada por la otra.
"""

import re
import uuid
from decimal import Decimal

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events import PRECIO_SUMINISTRO_CAMBIADO, bus
from app.core.tenancy import datos_autoria, require_organization_id
from app.core.visibilidad import organizaciones_visibles
from app.modules.catalogo.models import Familia, PrecioSuministro, Producto
from app.modules.catalogo.schemas import (
    FamiliaCreate,
    FamiliaUpdate,
    PrecioSuministroCreate,
    PrecioSuministroUpdate,
    ProductoCreate,
    ProductoUpdate,
)

PREFIJO_CODIGO = "P"
_RE_CODIGO = re.compile(rf"^{PREFIJO_CODIGO}(\d+)$")


class CodigoDuplicado(Exception):
    pass


class ProveedorInvalido(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    org_id = require_organization_id()
    codigos = await session.execute(
        select(Producto.codigo).where(Producto.organization_id == org_id)
    )
    maximo = 0
    for (codigo,) in codigos.all():
        match = _RE_CODIGO.match(codigo)
        if match:
            maximo = max(maximo, int(match.group(1)))
    return f"{PREFIJO_CODIGO}{maximo + 1:05d}"


# --- Familias ---


async def listar_familias(
    session: AsyncSession, *, creado_por_subject: str | None = None
) -> list[Familia]:
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    stmt = select(Familia).where(Familia.organization_id.in_(ids_visibles))
    if creado_por_subject is not None:
        stmt = stmt.where(Familia.creado_por_subject == creado_por_subject)
    rows = await session.execute(stmt.order_by(Familia.orden, Familia.codigo))
    return list(rows.scalars())


async def crear_familia(session: AsyncSession, datos: FamiliaCreate) -> Familia:
    org_id = require_organization_id()
    existe = await session.scalar(
        select(Familia.id).where(
            Familia.organization_id == org_id, Familia.codigo == datos.codigo
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe una familia con el código '{datos.codigo}'")
    familia = Familia(organization_id=org_id, **datos.model_dump(), **datos_autoria())
    session.add(familia)
    await session.flush()
    return familia


async def obtener_familia(session: AsyncSession, familia_id: uuid.UUID) -> Familia | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Familia).where(Familia.id == familia_id, Familia.organization_id == org_id)
    )


async def actualizar_familia(
    session: AsyncSession, familia_id: uuid.UUID, datos: FamiliaUpdate
) -> Familia | None:
    familia = await obtener_familia(session, familia_id)
    if familia is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(familia, campo, valor)
    await session.flush()
    return familia


async def eliminar_familia(session: AsyncSession, familia_id: uuid.UUID) -> bool:
    familia = await obtener_familia(session, familia_id)
    if familia is None:
        return False
    await session.delete(familia)
    await session.flush()
    return True


# --- Productos ---


def _filtrar(
    stmt: Select,
    q: str | None,
    tipo: str | None,
    familia_id: uuid.UUID | None,
    activo: bool | None,
) -> Select:
    if q:
        patron = f"%{q}%"
        stmt = stmt.where(
            or_(
                Producto.resumen.ilike(patron),
                Producto.codigo.ilike(patron),
                Producto.descripcion.ilike(patron),
                Producto.ean.ilike(patron),
            )
        )
    if tipo:
        stmt = stmt.where(Producto.tipo == tipo)
    if familia_id is not None:
        stmt = stmt.where(Producto.familia_id == familia_id)
    if activo is not None:
        stmt = stmt.where(Producto.activo.is_(activo))
    return stmt


async def listar_productos(
    session: AsyncSession,
    *,
    q: str | None = None,
    tipo: str | None = None,
    familia_id: uuid.UUID | None = None,
    activo: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Producto], int]:
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    base = select(Producto).where(Producto.organization_id.in_(ids_visibles))
    base = _filtrar(base, q, tipo, familia_id, activo)
    if creado_por_subject is not None:
        base = base.where(Producto.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    rows = await session.execute(
        base.order_by(Producto.codigo).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def obtener_producto(
    session: AsyncSession, producto_id: uuid.UUID
) -> Producto | None:
    """SOLO organización propia — uso interno de altas/ediciones/bajas y de
    cualquier validación antes de escribir. Para mostrar un producto
    (posiblemente compartido) al leer, usar `obtener_producto_visible`."""
    org_id = require_organization_id()
    producto = await session.scalar(
        select(Producto)
        .options(selectinload(Producto.suministros))
        .where(Producto.id == producto_id, Producto.organization_id == org_id)
    )
    if producto is not None:
        await _anotar_proveedores(session, producto.suministros)
    return producto


async def obtener_producto_visible(
    session: AsyncSession, producto_id: uuid.UUID
) -> Producto | None:
    """Para mostrar el detalle: propia organización o, si la cuenta
    comparte maestros, también el de una organización hermana."""
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    producto = await session.scalar(
        select(Producto)
        .options(selectinload(Producto.suministros))
        .where(Producto.id == producto_id, Producto.organization_id.in_(ids_visibles))
    )
    if producto is not None:
        await _anotar_proveedores(session, producto.suministros)
    return producto


async def _anotar_proveedores(
    session: AsyncSession, suministros: list[PrecioSuministro]
) -> None:
    """Adjunta la razón social del proveedor a cada tarifa.

    Atributo transitorio, no mapeado: evita una relación ORM entre módulos y
    ahorra al cliente una llamada por fila solo para pintar un nombre.
    """
    if not suministros:
        return
    from app.modules.terceros.models import Tercero

    ids = {s.proveedor_id for s in suministros}
    rows = await session.execute(
        select(Tercero.id, Tercero.razon_social).where(Tercero.id.in_(ids))
    )
    nombres = dict(rows.all())
    for suministro in suministros:
        suministro.proveedor_razon_social = nombres.get(suministro.proveedor_id)


async def crear_producto(session: AsyncSession, datos: ProductoCreate) -> Producto:
    org_id = require_organization_id()
    codigo = datos.codigo or await siguiente_codigo(session)
    existe = await session.scalar(
        select(Producto.id).where(
            Producto.organization_id == org_id, Producto.codigo == codigo
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe un producto con el código '{codigo}'")

    producto = Producto(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(producto)
    await session.flush()
    await session.refresh(producto, attribute_names=["suministros"])
    return producto


async def actualizar_producto(
    session: AsyncSession, producto_id: uuid.UUID, datos: ProductoUpdate
) -> Producto | None:
    producto = await obtener_producto(session, producto_id)
    if producto is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(producto, campo, valor)
    await session.flush()
    return producto


async def eliminar_producto(session: AsyncSession, producto_id: uuid.UUID) -> bool:
    producto = await obtener_producto(session, producto_id)
    if producto is None:
        return False
    await session.delete(producto)
    await session.flush()
    return True


# --- Precios de suministro ---


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


async def _limpiar_preferente(
    session: AsyncSession, producto_id: uuid.UUID, excepto: uuid.UUID | None = None
) -> None:
    """Solo puede haber una tarifa preferente por producto (índice parcial)."""
    stmt = (
        update(PrecioSuministro)
        .where(
            PrecioSuministro.producto_id == producto_id,
            PrecioSuministro.es_preferente.is_(True),
        )
        .values(es_preferente=False)
    )
    if excepto is not None:
        stmt = stmt.where(PrecioSuministro.id != excepto)
    await session.execute(stmt)


async def crear_suministro(
    session: AsyncSession, producto_id: uuid.UUID, datos: PrecioSuministroCreate
) -> PrecioSuministro | None:
    org_id = require_organization_id()
    producto = await session.scalar(
        select(Producto).where(
            Producto.id == producto_id, Producto.organization_id == org_id
        )
    )
    if producto is None:
        return None

    await _validar_proveedor(session, datos.proveedor_id)
    if datos.es_preferente:
        await _limpiar_preferente(session, producto_id)

    suministro = PrecioSuministro(
        organization_id=org_id, producto_id=producto_id, **datos.model_dump()
    )
    session.add(suministro)
    await session.flush()
    await bus.emit(PRECIO_SUMINISTRO_CAMBIADO, session=session, producto_id=producto_id)
    await _anotar_proveedores(session, [suministro])
    return suministro


async def obtener_suministro(
    session: AsyncSession, suministro_id: uuid.UUID
) -> PrecioSuministro | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(PrecioSuministro).where(
            PrecioSuministro.id == suministro_id,
            PrecioSuministro.organization_id == org_id,
        )
    )


async def actualizar_suministro(
    session: AsyncSession, suministro_id: uuid.UUID, datos: PrecioSuministroUpdate
) -> PrecioSuministro | None:
    suministro = await obtener_suministro(session, suministro_id)
    if suministro is None:
        return None

    cambios = datos.model_dump(exclude_unset=True)
    if "proveedor_id" in cambios and cambios["proveedor_id"] is not None:
        await _validar_proveedor(session, cambios["proveedor_id"])
    if cambios.get("es_preferente"):
        await _limpiar_preferente(session, suministro.producto_id, excepto=suministro.id)

    for campo, valor in cambios.items():
        setattr(suministro, campo, valor)
    await session.flush()
    await bus.emit(
        PRECIO_SUMINISTRO_CAMBIADO, session=session, producto_id=suministro.producto_id
    )
    await _anotar_proveedores(session, [suministro])
    return suministro


async def eliminar_suministro(session: AsyncSession, suministro_id: uuid.UUID) -> bool:
    suministro = await obtener_suministro(session, suministro_id)
    if suministro is None:
        return False
    producto_id = suministro.producto_id
    await session.delete(suministro)
    await session.flush()
    # Borrar la tarifa preferente cambia el precio de referencia, así que la
    # cascada tiene que dispararse igual que al crearla o modificarla.
    await bus.emit(PRECIO_SUMINISTRO_CAMBIADO, session=session, producto_id=producto_id)
    return True


async def precio_referencia(
    session: AsyncSession, producto_id: uuid.UUID
) -> Decimal | None:
    """Precio de suministro que usará el precio básico en Fase 2.

    Preferencia: la tarifa marcada como preferente; en su defecto, la vigente
    más reciente. Se devuelve neto de descuento y sin redondear.
    """
    org_id = require_organization_id()
    rows = await session.execute(
        select(PrecioSuministro)
        .where(
            PrecioSuministro.producto_id == producto_id,
            PrecioSuministro.organization_id == org_id,
            or_(
                PrecioSuministro.vigente_hasta.is_(None),
                PrecioSuministro.vigente_hasta >= func.current_date(),
            ),
        )
        .order_by(
            PrecioSuministro.es_preferente.desc(),
            PrecioSuministro.vigente_desde.desc(),
        )
        .limit(1)
    )
    suministro = rows.scalar_one_or_none()
    return suministro.precio_neto if suministro else None
