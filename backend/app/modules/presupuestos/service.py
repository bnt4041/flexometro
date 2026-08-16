import re
import uuid
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redondeo import redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.core.visibilidad import organizaciones_visibles
from app.modules.presupuestos import calculo
from app.modules.presupuestos.models import (
    Concepto,
    Descomposicion,
    OrigenPrecio,
    TipoConcepto,
)
from app.modules.presupuestos.schemas import (
    ConceptoCreate,
    ConceptoUpdate,
    LineaCreate,
    LineaOut,
    LineaUpdate,
    NodoArbol,
    UsoOut,
)

# Prefijo de código por tipo. FIEBDC-3 marca los auxiliares con '%' al final
# del código; ese sufijo se añade al exportar (Fase 5), no se guarda, para que
# el código no cambie si el concepto cambia de tipo.
PREFIJOS = {
    TipoConcepto.BASICO: "B",
    TipoConcepto.AUXILIAR: "A",
    TipoConcepto.UNITARIO: "U",
}


class CodigoDuplicado(Exception):
    pass


class ConceptoEnUso(Exception):
    pass


class HijoInvalido(Exception):
    pass


async def siguiente_codigo(session: AsyncSession, tipo: TipoConcepto) -> str:
    org_id = require_organization_id()
    prefijo = PREFIJOS[tipo]
    patron = re.compile(rf"^{prefijo}(\d+)$")
    codigos = await session.execute(
        select(Concepto.codigo).where(
            Concepto.organization_id == org_id, Concepto.tipo == tipo
        )
    )
    maximo = 0
    for (codigo,) in codigos.all():
        encaje = patron.match(codigo)
        if encaje:
            maximo = max(maximo, int(encaje.group(1)))
    return f"{prefijo}{maximo + 1:05d}"


def _filtrar(stmt: Select, q: str | None, tipo: str | None, activo: bool | None) -> Select:
    if q:
        patron = f"%{q}%"
        stmt = stmt.where(
            or_(
                Concepto.resumen.ilike(patron),
                Concepto.codigo.ilike(patron),
                Concepto.texto.ilike(patron),
            )
        )
    if tipo:
        stmt = stmt.where(Concepto.tipo == tipo)
    if activo is not None:
        stmt = stmt.where(Concepto.activo.is_(activo))
    return stmt


async def listar_conceptos(
    session: AsyncSession,
    *,
    q: str | None = None,
    tipo: str | None = None,
    activo: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Concepto], int]:
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    base = select(Concepto).where(Concepto.organization_id.in_(ids_visibles))
    base = _filtrar(base, q, tipo, activo)
    if creado_por_subject is not None:
        base = base.where(Concepto.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    filas = await session.execute(
        base.order_by(Concepto.tipo, Concepto.codigo).limit(limit).offset(offset)
    )
    return list(filas.scalars()), int(total or 0)


async def obtener_concepto(
    session: AsyncSession, concepto_id: uuid.UUID
) -> Concepto | None:
    """SOLO organización propia — uso interno de altas/ediciones/bajas y de
    cualquier función que valide propiedad antes de escribir. Para mostrar
    un concepto (posiblemente compartido) al leer, usar
    `obtener_concepto_visible`."""
    org_id = require_organization_id()
    return await session.scalar(
        select(Concepto)
        .options(selectinload(Concepto.lineas).selectinload(Descomposicion.hijo))
        .where(Concepto.id == concepto_id, Concepto.organization_id == org_id)
    )


async def obtener_concepto_visible(
    session: AsyncSession, concepto_id: uuid.UUID
) -> Concepto | None:
    """Para mostrar el detalle (y expandir el árbol de descomposición, ver
    `arbol()`): propia organización o, si la cuenta comparte maestros,
    también el de una organización hermana."""
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    return await session.scalar(
        select(Concepto)
        .options(selectinload(Concepto.lineas).selectinload(Descomposicion.hijo))
        .where(Concepto.id == concepto_id, Concepto.organization_id.in_(ids_visibles))
    )


async def crear_concepto(session: AsyncSession, datos: ConceptoCreate) -> Concepto:
    org_id = require_organization_id()
    codigo = datos.codigo or await siguiente_codigo(session, datos.tipo)
    existe = await session.scalar(
        select(Concepto.id).where(
            Concepto.organization_id == org_id, Concepto.codigo == codigo
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe un concepto con el código '{codigo}'")

    concepto = Concepto(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(concepto)
    await session.flush()

    # Un concepto recién creado sin hijos vale 0 salvo que su precio sea manual
    # o venga del catálogo; en esos dos casos hay que resolverlo ya.
    if concepto.origen_precio != OrigenPrecio.MANUAL:
        concepto.precio = await calculo.calcular_precio(session, concepto)
        await session.flush()

    await session.refresh(concepto, attribute_names=["lineas"])
    return concepto


async def actualizar_concepto(
    session: AsyncSession, concepto_id: uuid.UUID, datos: ConceptoUpdate
) -> Concepto | None:
    concepto = await obtener_concepto(session, concepto_id)
    if concepto is None:
        return None

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(concepto, campo, valor)
    if "precio" in cambios and concepto.origen_precio == OrigenPrecio.MANUAL:
        concepto.precio = redondear_precio(concepto.precio)
    await session.flush()

    # Cualquiera de estos tres cambia el precio del concepto y, por tanto, el de
    # todo lo que lo contiene.
    if {"precio", "origen_precio", "costes_indirectos", "producto_id"} & cambios.keys():
        await calculo.recalcular_cascada(session, concepto.id)

    return concepto


async def eliminar_concepto(session: AsyncSession, concepto_id: uuid.UUID) -> bool:
    concepto = await obtener_concepto(session, concepto_id)
    if concepto is None:
        return False
    try:
        await session.delete(concepto)
        await session.flush()
    except IntegrityError as exc:
        # La FK de descomposicion.hijo_id es RESTRICT: si alguien lo usa, no se
        # borra en silencio dejando descompuestos incompletos.
        raise ConceptoEnUso(
            "No se puede eliminar: el concepto forma parte de otros descompuestos"
        ) from exc
    return True


# --- Líneas del descompuesto ---


async def anadir_linea(
    session: AsyncSession, padre_id: uuid.UUID, datos: LineaCreate
) -> Descomposicion | None:
    org_id = require_organization_id()
    padre = await session.scalar(
        select(Concepto).where(
            Concepto.id == padre_id, Concepto.organization_id == org_id
        )
    )
    if padre is None:
        return None

    hijo = await session.scalar(
        select(Concepto).where(
            Concepto.id == datos.hijo_id, Concepto.organization_id == org_id
        )
    )
    if hijo is None:
        raise HijoInvalido("El concepto hijo no existe en esta organización")

    if await calculo.crearia_ciclo(session, padre_id, datos.hijo_id):
        raise calculo.CicloDetectado(
            f"'{hijo.codigo}' contiene directa o indirectamente a '{padre.codigo}': "
            "añadirlo cerraría un ciclo"
        )

    linea = Descomposicion(organization_id=org_id, padre_id=padre_id, **datos.model_dump())
    session.add(linea)

    # Descomponer un concepto implica que su precio pasa a calcularse: dejarlo
    # en manual sería tener un descompuesto que no suma a su propio precio.
    if padre.origen_precio != OrigenPrecio.DESCOMPOSICION:
        padre.origen_precio = OrigenPrecio.DESCOMPOSICION
    await session.flush()

    await calculo.recalcular_cascada(session, padre_id)
    return linea


async def obtener_linea(session: AsyncSession, linea_id: uuid.UUID) -> Descomposicion | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Descomposicion).where(
            Descomposicion.id == linea_id, Descomposicion.organization_id == org_id
        )
    )


async def actualizar_linea(
    session: AsyncSession, linea_id: uuid.UUID, datos: LineaUpdate
) -> Descomposicion | None:
    linea = await obtener_linea(session, linea_id)
    if linea is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(linea, campo, valor)
    await session.flush()
    await calculo.recalcular_cascada(session, linea.padre_id)
    return linea


async def eliminar_linea(session: AsyncSession, linea_id: uuid.UUID) -> bool:
    linea = await obtener_linea(session, linea_id)
    if linea is None:
        return False
    padre_id = linea.padre_id
    await session.delete(linea)
    await session.flush()
    await calculo.recalcular_cascada(session, padre_id)
    return True


# --- Proyecciones ---


def lineas_de(concepto: Concepto) -> list[LineaOut]:
    return [
        LineaOut(
            id=linea.id,
            hijo_id=linea.hijo_id,
            hijo_codigo=linea.hijo.codigo,
            hijo_resumen=linea.hijo.resumen,
            hijo_unidad=linea.hijo.unidad,
            hijo_tipo=linea.hijo.tipo,
            hijo_precio=linea.hijo.precio,
            rendimiento=linea.rendimiento,
            factor=linea.factor,
            orden=linea.orden,
            importe=redondear_precio(linea.rendimiento * linea.factor * linea.hijo.precio),
        )
        for linea in concepto.lineas
    ]


def clase_de(concepto: Concepto) -> str | None:
    """Simple, complejo o funcional, según Ramírez de Arellano.

    Es una lectura de la estructura, no un dato: un unitario descompuesto solo
    en básicos es simple; si entra algún auxiliar es complejo; y si agrupa otros
    unitarios es funcional.
    """
    if concepto.tipo != TipoConcepto.UNITARIO:
        return None
    tipos = {linea.hijo.tipo for linea in concepto.lineas}
    if not tipos:
        return None
    if TipoConcepto.UNITARIO in tipos:
        return "funcional"
    if TipoConcepto.AUXILIAR in tipos:
        return "complejo"
    return "simple"


def coste_directo_de(lineas: list[LineaOut]) -> Decimal:
    return redondear_precio(sum((linea.importe for linea in lineas), Decimal("0.00")))


async def donde_se_usa(session: AsyncSession, concepto_id: uuid.UUID) -> list[UsoOut]:
    """Deliberadamente estricto a la organización propia (Fase 15): a
    diferencia de `arbol()`, esto también hace de guarda antes de borrar
    (`ConceptoEnUso`), y mezclar ahí referencias de una organización
    hermana complicaría esa comprobación sin que nadie lo haya pedido
    todavía. Navegar "hacia arriba" desde un concepto compartido queda
    fuera de esta primera versión."""
    usos = await calculo.donde_se_usa(session, concepto_id)
    return [
        UsoOut(
            id=concepto.id,
            codigo=concepto.codigo,
            resumen=concepto.resumen,
            tipo=concepto.tipo,
            precio=concepto.precio,
            rendimiento=rendimiento,
        )
        for concepto, rendimiento in usos
    ]


async def arbol(
    session: AsyncSession,
    concepto_id: uuid.UUID,
    *,
    profundidad: int = 6,
) -> NodoArbol | None:
    """Descompuesto completo, expandido recursivamente. Solo lectura — usa
    `obtener_concepto_visible`, así que un concepto compartido (Fase 15)
    expande su árbol aunque algún hijo pertenezca a una organización
    hermana."""
    concepto = await obtener_concepto_visible(session, concepto_id)
    if concepto is None:
        return None
    return await _nodo(session, concepto, None, None, profundidad)


async def _nodo(
    session: AsyncSession,
    concepto: Concepto,
    rendimiento: Decimal | None,
    factor: Decimal | None,
    profundidad: int,
) -> NodoArbol:
    nodo = NodoArbol(
        id=concepto.id,
        codigo=concepto.codigo,
        resumen=concepto.resumen,
        unidad=concepto.unidad,
        tipo=concepto.tipo,
        precio=concepto.precio,
        rendimiento=rendimiento,
        factor=factor,
        importe=(
            redondear_precio(rendimiento * (factor or Decimal("1")) * concepto.precio)
            if rendimiento is not None
            else None
        ),
    )
    if profundidad <= 0:
        return nodo
    for linea in concepto.lineas:
        hijo = await obtener_concepto_visible(session, linea.hijo_id)
        if hijo is None:
            continue
        nodo.hijos.append(
            await _nodo(session, hijo, linea.rendimiento, linea.factor, profundidad - 1)
        )
    return nodo
