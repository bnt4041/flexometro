import re
import uuid
from decimal import Decimal

from sqlalchemy import Select, func, or_, select, update
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
    Familia,
    HistoricoPrecioConcepto,
    OrigenPrecio,
    PrecioSuministro,
    TipoConcepto,
)
from app.modules.presupuestos.models_presupuesto import Partida, Presupuesto
from app.modules.presupuestos.schemas import (
    ConceptoCreate,
    ConceptoUpdate,
    FamiliaCreate,
    FamiliaUpdate,
    HistoricoPrecioOut,
    LineaCreate,
    LineaOut,
    LineaUpdate,
    NodoArbol,
    PartidaUsoOut,
    PrecioSuministroCreate,
    PrecioSuministroUpdate,
    UsoCompletoOut,
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


class ProveedorInvalido(Exception):
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
                Concepto.ean.ilike(patron),
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
    concepto = await session.scalar(
        select(Concepto)
        .options(
            selectinload(Concepto.lineas).selectinload(Descomposicion.hijo),
            selectinload(Concepto.suministros),
        )
        .where(Concepto.id == concepto_id, Concepto.organization_id == org_id)
    )
    if concepto is not None:
        await _anotar_proveedores(session, concepto.suministros)
    return concepto


async def obtener_concepto_visible(
    session: AsyncSession, concepto_id: uuid.UUID
) -> Concepto | None:
    """Para mostrar el detalle (y expandir el árbol de descomposición, ver
    `arbol()`): propia organización o, si la cuenta comparte maestros,
    también el de una organización hermana."""
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    concepto = await session.scalar(
        select(Concepto)
        .options(
            selectinload(Concepto.lineas).selectinload(Descomposicion.hijo),
            selectinload(Concepto.suministros),
        )
        .where(Concepto.id == concepto_id, Concepto.organization_id.in_(ids_visibles))
    )
    if concepto is not None:
        await _anotar_proveedores(session, concepto.suministros)
    return concepto


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
    # o venga de una tarifa de proveedor; en esos dos casos hay que resolverlo ya.
    if concepto.origen_precio != OrigenPrecio.MANUAL:
        concepto.precio = await calculo.calcular_precio(session, concepto)
        await session.flush()

    # Primera fila del histórico: el precio de alta también es un precio que
    # el concepto "ha tenido".
    await calculo.registrar_historico(session, concepto)
    await session.flush()

    await session.refresh(concepto, attribute_names=["lineas", "suministros"])
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
        # Una edición manual no cambia origen_precio ni dispara la rama
        # "nuevo != concepto.precio" de `recalcular_cascada` (el valor ya
        # está escrito), así que el histórico se anota aquí a propósito.
        await calculo.registrar_historico(session, concepto)
    await session.flush()

    # Cualquiera de estos cambia el precio del concepto y, por tanto, el de
    # todo lo que lo contiene.
    if {"precio", "origen_precio", "costes_indirectos"} & cambios.keys():
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


async def pegar_lineas(
    session: AsyncSession, padre_id: uuid.UUID, linea_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve líneas de descompuesto de otra ficha (o de la misma) a
    `padre_id` — la versión para el banco de precios de
    `presupuesto_service.pegar_componentes_descompuesto`. Sin nada que
    independizar antes: el descompuesto de una ficha del banco siempre es
    propio."""
    org_id = require_organization_id()
    padre = await session.scalar(
        select(Concepto).where(Concepto.id == padre_id, Concepto.organization_id == org_id)
    )
    if padre is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(Descomposicion).where(
                    Descomposicion.id.in_(linea_ids),
                    Descomposicion.organization_id == org_id,
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {l.id: l for l in origen}
    orden_pedido = [origen_por_id[lid] for lid in linea_ids if lid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(Descomposicion.orden)).where(Descomposicion.padre_id == padre_id)
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    padres_origen: set[uuid.UUID] = set()
    pegadas = 0
    for linea in orden_pedido:
        padres_origen.add(linea.padre_id)
        # Ni contra sí misma ni cerrando un ciclo indirecto — igual que
        # `anadir_linea`, que es justo lo que evita esto al pegar a mano.
        if linea.hijo_id == padre_id or await calculo.crearia_ciclo(
            session, padre_id, linea.hijo_id
        ):
            continue
        if alcance == "mover":
            linea.padre_id = padre_id
            linea.orden = orden
        else:
            session.add(
                Descomposicion(
                    organization_id=org_id,
                    padre_id=padre_id,
                    hijo_id=linea.hijo_id,
                    rendimiento=linea.rendimiento,
                    factor=linea.factor,
                    orden=orden,
                )
            )
        orden += 1
        pegadas += 1

    if pegadas and padre.origen_precio != OrigenPrecio.DESCOMPOSICION:
        padre.origen_precio = OrigenPrecio.DESCOMPOSICION
    await session.flush()

    if pegadas:
        await calculo.recalcular_cascada(session, padre_id)
    if alcance == "mover":
        for origen_id in padres_origen - {padre_id}:
            await calculo.recalcular_cascada(session, origen_id)
    return pegadas


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


async def _limpiar_preferente(
    session: AsyncSession, concepto_id: uuid.UUID, excepto: uuid.UUID | None = None
) -> None:
    """Solo puede haber una tarifa preferente por concepto (índice parcial)."""
    stmt = (
        update(PrecioSuministro)
        .where(
            PrecioSuministro.concepto_id == concepto_id,
            PrecioSuministro.es_preferente.is_(True),
        )
        .values(es_preferente=False)
    )
    if excepto is not None:
        stmt = stmt.where(PrecioSuministro.id != excepto)
    await session.execute(stmt)


async def _recalcular_si_producto(session: AsyncSession, concepto_id: uuid.UUID) -> None:
    """Una tarifa que cambia solo mueve el precio si el concepto la usa como
    origen; si el concepto está en manual o descomposición, no hay nada que
    recalcular todavía (pero puede pasar a usarla más tarde)."""
    concepto = await session.get(Concepto, concepto_id)
    if concepto is not None and concepto.origen_precio == OrigenPrecio.PRODUCTO:
        await calculo.recalcular_cascada(session, concepto_id)


async def crear_suministro(
    session: AsyncSession, concepto_id: uuid.UUID, datos: PrecioSuministroCreate
) -> PrecioSuministro | None:
    org_id = require_organization_id()
    concepto = await session.scalar(
        select(Concepto).where(
            Concepto.id == concepto_id, Concepto.organization_id == org_id
        )
    )
    if concepto is None:
        return None

    await _validar_proveedor(session, datos.proveedor_id)
    if datos.es_preferente:
        await _limpiar_preferente(session, concepto_id)

    suministro = PrecioSuministro(
        organization_id=org_id, concepto_id=concepto_id, **datos.model_dump()
    )
    session.add(suministro)
    await session.flush()
    await _recalcular_si_producto(session, concepto_id)
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
        await _limpiar_preferente(session, suministro.concepto_id, excepto=suministro.id)

    for campo, valor in cambios.items():
        setattr(suministro, campo, valor)
    await session.flush()
    await _recalcular_si_producto(session, suministro.concepto_id)
    await _anotar_proveedores(session, [suministro])
    return suministro


async def eliminar_suministro(session: AsyncSession, suministro_id: uuid.UUID) -> bool:
    suministro = await obtener_suministro(session, suministro_id)
    if suministro is None:
        return False
    concepto_id = suministro.concepto_id
    await session.delete(suministro)
    await session.flush()
    # Borrar la tarifa preferente cambia el precio de referencia, así que la
    # cascada tiene que dispararse igual que al crearla o modificarla.
    await _recalcular_si_producto(session, concepto_id)
    return True


# --- Histórico de precios ---


async def historico_de(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[HistoricoPrecioOut]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(HistoricoPrecioConcepto)
        .where(
            HistoricoPrecioConcepto.concepto_id == concepto_id,
            HistoricoPrecioConcepto.organization_id == org_id,
        )
        .order_by(HistoricoPrecioConcepto.fecha.desc())
    )
    return [HistoricoPrecioOut.model_validate(h) for h in filas.scalars()]


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


async def _en_partidas_de(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[PartidaUsoOut]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(Partida, Presupuesto.nombre, Presupuesto.estado)
        .join(Presupuesto, Presupuesto.id == Partida.presupuesto_id)
        .where(Partida.concepto_id == concepto_id, Partida.organization_id == org_id)
        .order_by(Presupuesto.nombre, Partida.codigo)
    )
    return [
        PartidaUsoOut(
            id=partida.id,
            presupuesto_id=partida.presupuesto_id,
            presupuesto_nombre=nombre,
            presupuesto_estado=estado,
            codigo=partida.codigo,
            resumen=partida.resumen,
            medicion=partida.medicion,
            precio=partida.precio,
            importe=partida.importe,
        )
        for partida, nombre, estado in filas.all()
    ]


async def donde_se_usa(session: AsyncSession, concepto_id: uuid.UUID) -> UsoCompletoOut:
    """Dónde participa este concepto: en descompuestos de otros conceptos
    (directa o indirectamente) y en partidas de presupuestos concretos.

    Deliberadamente estricto a la organización propia (Fase 15): a diferencia
    de `arbol()`, esto también hace de guarda antes de borrar
    (`ConceptoEnUso`), y mezclar ahí referencias de una organización hermana
    complicaría esa comprobación sin que nadie lo haya pedido todavía.
    """
    usos = await calculo.donde_se_usa(session, concepto_id)
    en_descomposiciones = [
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
    en_partidas = await _en_partidas_de(session, concepto_id)
    return UsoCompletoOut(en_descomposiciones=en_descomposiciones, en_partidas=en_partidas)


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
