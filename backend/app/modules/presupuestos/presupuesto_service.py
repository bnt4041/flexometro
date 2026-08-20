import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.numeracion import siguiente_referencia
from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.presupuestos import calculo, formulas
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos.models import (
    Concepto,
    Descomposicion,
    NaturalezaConcepto,
    OrigenPrecio,
    TipoConcepto,
)
from app.modules.presupuestos.models_presupuesto import (
    ESTADOS_BLOQUEADOS,
    Capitulo,
    EstadoPresupuesto,
    FormulaMedicion,
    LineaMedicion,
    MetodoCalculo,
    Partida,
    PartidaDescomposicion,
    Presupuesto,
)
from app.modules.presupuestos.presupuesto_schemas import (
    CambioLinea,
    CapituloCreate,
    CapituloUpdate,
    FormulaMedicionCreate,
    FormulaMedicionUpdate,
    LineaMedicionCreate,
    LineaMedicionUpdate,
    NodoCapitulo,
    PartidaCreate,
    PartidaOut,
    PartidaUpdate,
    PresupuestoCreate,
    PresupuestoUpdate,
    RecursoAgregado,
    RecursosPresupuesto,
    TotalesOut,
)

class CodigoDuplicado(Exception):
    pass


class ConceptoInvalido(Exception):
    pass


class PartidaSinDatos(Exception):
    pass


class ConceptoYaVinculado(Exception):
    pass


class FormulaNoEncontrada(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    """Fase 16: patrón configurable por cuenta (Administración → ficha de
    cuenta → Numeración), en vez del prefijo "PRE" fijo de antes."""
    org_id = require_organization_id()
    return await siguiente_referencia(session, organization_id=org_id, tipo_documento="presupuesto")


# --- Presupuesto ---


async def listar(
    session: AsyncSession,
    *,
    q: str | None = None,
    estado: str | None = None,
    es_plantilla: bool = False,
    solo_ultima_version: bool = False,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Presupuesto], int]:
    org_id = require_organization_id()
    # Las plantillas no se mezclan con los presupuestos reales en el listado:
    # comparten tabla, pero no son lo mismo para quien mira la pantalla.
    base = select(Presupuesto).where(
        Presupuesto.organization_id == org_id,
        Presupuesto.es_plantilla.is_(es_plantilla),
    )
    if solo_ultima_version:
        # De cada línea de versiones, solo la más alta. La línea se identifica
        # por raiz_id, que en la primera versión es nulo y vale su propio id.
        otro = aliased(Presupuesto)
        mi_linea = func.coalesce(Presupuesto.raiz_id, Presupuesto.id)
        ultima_version = (
            select(func.max(otro.version))
            .where(
                otro.organization_id == org_id,
                otro.es_plantilla.is_(es_plantilla),
                func.coalesce(otro.raiz_id, otro.id) == mi_linea,
            )
            .scalar_subquery()
        )
        base = base.where(Presupuesto.version == ultima_version)
    if q:
        patron = f"%{q}%"
        base = base.where(
            or_(
                Presupuesto.nombre.ilike(patron),
                Presupuesto.codigo.ilike(patron),
                Presupuesto.emplazamiento.ilike(patron),
            )
        )
    if estado:
        base = base.where(Presupuesto.estado == estado)
    if creado_por_subject is not None:
        base = base.where(Presupuesto.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    filas = await session.execute(
        base.order_by(Presupuesto.codigo.desc()).limit(limit).offset(offset)
    )
    return list(filas.scalars()), int(total or 0)


async def obtener(session: AsyncSession, presupuesto_id: uuid.UUID) -> Presupuesto | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Presupuesto).where(
            Presupuesto.id == presupuesto_id, Presupuesto.organization_id == org_id
        )
    )


async def crear(session: AsyncSession, datos: PresupuestoCreate) -> Presupuesto:
    org_id = require_organization_id()
    codigo = datos.codigo or await siguiente_codigo(session)
    existe = await session.scalar(
        select(Presupuesto.id).where(
            Presupuesto.organization_id == org_id, Presupuesto.codigo == codigo
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe un presupuesto con el código '{codigo}'")

    presupuesto = Presupuesto(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(presupuesto)
    await session.flush()
    return presupuesto


async def actualizar(
    session: AsyncSession, presupuesto_id: uuid.UUID, datos: PresupuestoUpdate
) -> Presupuesto | None:
    presupuesto = await obtener(session, presupuesto_id)
    if presupuesto is None:
        return None

    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(presupuesto, campo, valor)

    # Salir de borrador congela los precios; volver a borrador los descongela.
    # Si el cliente ha pedido explícitamente un valor, manda el suyo.
    if "estado" in cambios and "precios_bloqueados" not in cambios:
        presupuesto.precios_bloqueados = presupuesto.estado in ESTADOS_BLOQUEADOS

    await session.flush()

    # Tocar el método o cualquiera de sus porcentajes cambia la venta de todas
    # las partidas que no estén bloqueadas (Fase 35).
    if cambios.keys() & {
        "metodo_calculo",
        "porcentaje_metodo",
        "gastos_generales",
        "beneficio_industrial",
    }:
        await calc.recalcular_ventas(session, presupuesto)

    return presupuesto


async def eliminar(session: AsyncSession, presupuesto_id: uuid.UUID) -> bool:
    presupuesto = await obtener(session, presupuesto_id)
    if presupuesto is None:
        return False
    await session.delete(presupuesto)
    await session.flush()
    return True


# --- Capítulos ---


async def _siguiente_codigo_capitulo(
    session: AsyncSession, presupuesto_id: uuid.UUID, parent_id: uuid.UUID | None
) -> str:
    """Numeración jerárquica: 01, 02 en la raíz; 01.01, 01.02 dentro de 01."""
    hermanos = (
        await session.execute(
            select(Capitulo.codigo).where(
                Capitulo.presupuesto_id == presupuesto_id,
                Capitulo.parent_id.is_(None) if parent_id is None else Capitulo.parent_id == parent_id,
            )
        )
    ).scalars()

    prefijo = ""
    if parent_id is not None:
        padre = await session.get(Capitulo, parent_id)
        if padre is not None:
            prefijo = f"{padre.codigo}."

    maximo = 0
    for codigo in hermanos:
        ultimo = codigo.rsplit(".", 1)[-1]
        if ultimo.isdigit():
            maximo = max(maximo, int(ultimo))
    return f"{prefijo}{maximo + 1:02d}"


async def obtener_capitulo(session: AsyncSession, capitulo_id: uuid.UUID) -> Capitulo | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Capitulo).where(Capitulo.id == capitulo_id, Capitulo.organization_id == org_id)
    )


async def crear_capitulo(
    session: AsyncSession, presupuesto_id: uuid.UUID, datos: CapituloCreate
) -> Capitulo | None:
    org_id = require_organization_id()
    presupuesto = await obtener(session, presupuesto_id)
    if presupuesto is None:
        return None

    codigo = datos.codigo or await _siguiente_codigo_capitulo(
        session, presupuesto_id, datos.parent_id
    )
    capitulo = Capitulo(
        organization_id=org_id,
        presupuesto_id=presupuesto_id,
        **{**datos.model_dump(exclude={"codigo"}), "codigo": codigo},
    )
    session.add(capitulo)
    await session.flush()
    return capitulo


async def actualizar_capitulo(
    session: AsyncSession, capitulo_id: uuid.UUID, datos: CapituloUpdate
) -> Capitulo | None:
    capitulo = await obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(capitulo, campo, valor)
    await session.flush()
    return capitulo


async def eliminar_capitulo(session: AsyncSession, capitulo_id: uuid.UUID) -> bool:
    capitulo = await obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        return False
    await session.delete(capitulo)
    await session.flush()
    return True


# --- Partidas ---


async def crear_partida(
    session: AsyncSession, capitulo_id: uuid.UUID, datos: PartidaCreate
) -> Partida | None:
    org_id = require_organization_id()
    capitulo = await session.scalar(
        select(Capitulo).where(
            Capitulo.id == capitulo_id, Capitulo.organization_id == org_id
        )
    )
    if capitulo is None:
        return None

    codigo, resumen, unidad, precio, texto = (
        datos.codigo,
        datos.resumen,
        datos.unidad,
        datos.precio,
        datos.texto,
    )

    if datos.concepto_id is not None:
        concepto = await session.scalar(
            select(Concepto).where(
                Concepto.id == datos.concepto_id, Concepto.organization_id == org_id
            )
        )
        if concepto is None:
            raise ConceptoInvalido("El concepto no existe en esta organización")
        # Copia del cuadro: es lo que permite que un presupuesto emitido siga
        # diciendo lo que decía aunque el cuadro cambie después.
        codigo = codigo or concepto.codigo
        resumen = resumen or concepto.resumen
        unidad = unidad or concepto.unidad
        precio = precio if precio is not None else concepto.precio
        texto = texto if texto is not None else concepto.texto
    elif not resumen:
        raise PartidaSinDatos(
            "Una partida alzada necesita al menos descripción; sin concepto no hay de dónde copiarla"
        )

    partida = Partida(
        organization_id=org_id,
        presupuesto_id=capitulo.presupuesto_id,
        capitulo_id=capitulo_id,
        concepto_id=datos.concepto_id,
        codigo=codigo or "",
        resumen=resumen or "",
        texto=texto,
        unidad=unidad or "ud",
        precio=redondear_precio(precio if precio is not None else Decimal("0")),
        orden=datos.orden,
    )
    session.add(partida)
    await session.flush()

    for linea in datos.lineas:
        session.add(_nueva_linea(org_id, partida.id, linea))
    await session.flush()
    await calc.recalcular_partida(session, partida)
    presupuesto = await obtener(session, capitulo.presupuesto_id)
    if presupuesto is not None:
        calc.aplicar_venta(presupuesto, partida)
        await session.flush()
    return partida


async def obtener_partida(session: AsyncSession, partida_id: uuid.UUID) -> Partida | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Partida)
        .options(selectinload(Partida.lineas))
        .where(Partida.id == partida_id, Partida.organization_id == org_id)
    )


async def actualizar_partida(
    session: AsyncSession, partida_id: uuid.UUID, datos: PartidaUpdate
) -> Partida | None:
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)

    # La medición escrita a mano solo vale en partidas sin desglose: con
    # líneas, la medición es la suma de sus parciales y el recálculo la
    # sobrescribiría de todas formas, así que se ignora en silencio en vez de
    # aceptar un valor que va a durar hasta el siguiente flush.
    medicion_manual = cambios.pop("medicion", None)
    sin_desglose = not await _tiene_desglose(session, partida.id)

    for campo, valor in cambios.items():
        setattr(partida, campo, valor)
    if "precio" in cambios:
        partida.precio = redondear_precio(partida.precio)

    if medicion_manual is not None and sin_desglose:
        partida.medicion = redondear_medicion(medicion_manual)
        partida.importe = redondear_precio(partida.medicion * partida.precio)
        await _refrescar_venta(session, partida)
        return partida

    await session.flush()
    await calc.recalcular_partida(session, partida)
    await _refrescar_venta(session, partida)
    return partida


async def _tiene_desglose(session: AsyncSession, partida_id: uuid.UUID) -> bool:
    """¿La partida tiene líneas de medición?

    Se consulta a la base de datos en vez de mirar `partida.lineas`: si el
    objeto ya estaba en la sesión con la colección cargada, `selectinload` no
    la refresca al volver a pedirlo, y quedarían líneas fantasma tras un
    borrado. Con una sola edición por request casi nunca se nota, pero cuando
    se nota el síntoma es desconcertante.
    """
    total = await session.scalar(
        select(func.count())
        .select_from(LineaMedicion)
        .where(LineaMedicion.partida_id == partida_id)
    )
    return bool(total)


async def _refrescar_venta(session: AsyncSession, partida: Partida) -> None:
    """Rehace la venta de la partida tras cambiarle coste o medición (Fase 35).
    Si está bloqueada solo se refresca el importe, no el precio."""
    presupuesto = await obtener(session, partida.presupuesto_id)
    if presupuesto is not None:
        calc.aplicar_venta(presupuesto, partida)
    await session.flush()


async def eliminar_partida(session: AsyncSession, partida_id: uuid.UUID) -> bool:
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    await session.delete(partida)
    await session.flush()
    return True


# --- Portapapeles: copiar/mover entre capítulos y entre partidas (Fase 1b) ---
#
# Los tres reciben una lista de ids "de origen" (de cualquier capítulo o
# partida de la misma organización, del mismo presupuesto o de otro — la
# fase 1b los usa solo dentro del mismo, pero nada aquí lo exige) y solo
# actúan sobre los que de verdad existen y son de la organización actual: el
# resto se cuentan como "no pegados" en vez de fallar entero, para que
# arrastrar una selección con algo ya borrado entretanto no tire todo el
# pegado abajo.


async def pegar_partidas(
    session: AsyncSession, capitulo_id: uuid.UUID, partida_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve partidas enteras a otro capítulo.

    Copiar clona la partida, su descompuesto propio (si lo tiene) y sus
    líneas de medición, todo con ids nuevos — el banco de precios no se toca.
    Mover solo reengancha `capitulo_id`/`presupuesto_id`: lo que cuelga de la
    partida ya es suyo, no hay nada que clonar.
    """
    org_id = require_organization_id()
    capitulo = await session.scalar(
        select(Capitulo).where(Capitulo.id == capitulo_id, Capitulo.organization_id == org_id)
    )
    if capitulo is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(Partida).where(
                    Partida.id.in_(partida_ids), Partida.organization_id == org_id
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {p.id: p for p in origen}
    orden_pedido = [origen_por_id[pid] for pid in partida_ids if pid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(Partida.orden)).where(Partida.capitulo_id == capitulo_id)
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    afectadas: list[Partida] = []
    for partida in orden_pedido:
        if alcance == "mover":
            partida.capitulo_id = capitulo_id
            partida.presupuesto_id = capitulo.presupuesto_id
            partida.orden = orden
            afectadas.append(partida)
        else:
            nueva = await _clonar_partida(
                session, partida, org_id, capitulo.presupuesto_id, capitulo_id, orden
            )
            afectadas.append(nueva)
        orden += 1

    await session.flush()
    for p in afectadas:
        await _refrescar_venta(session, p)
    return len(afectadas)


async def _clonar_partida(
    session: AsyncSession,
    partida: Partida,
    org_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    capitulo_id: uuid.UUID,
    orden: int,
) -> Partida:
    """Clona una partida entera —descompuesto propio y mediciones incluidos—
    con ids nuevos, en el capítulo indicado. Compartido por `pegar_partidas`
    y `_clonar_capitulo` (copiar un capítulo copia también sus partidas)."""
    nueva = Partida(
        organization_id=org_id,
        presupuesto_id=presupuesto_id,
        capitulo_id=capitulo_id,
        concepto_id=partida.concepto_id,
        codigo=partida.codigo,
        resumen=partida.resumen,
        texto=partida.texto,
        unidad=partida.unidad,
        precio=partida.precio,
        costes_indirectos=partida.costes_indirectos,
        precio_venta=partida.precio_venta,
        # Un precio pactado a mano en el origen no se hereda: es un candado
        # puesto para ESA partida, no para la copia.
        venta_bloqueada=False,
        importe_venta=partida.importe_venta,
        medicion=partida.medicion,
        importe=partida.importe,
        orden=orden,
    )
    session.add(nueva)
    await session.flush()

    propias = (
        await session.execute(
            select(PartidaDescomposicion)
            .where(PartidaDescomposicion.partida_id == partida.id)
            .order_by(PartidaDescomposicion.orden)
        )
    ).scalars()
    for linea in propias:
        session.add(
            PartidaDescomposicion(
                organization_id=org_id,
                partida_id=nueva.id,
                hijo_id=linea.hijo_id,
                codigo=linea.codigo,
                resumen=linea.resumen,
                unidad=linea.unidad,
                naturaleza=linea.naturaleza,
                rendimiento=linea.rendimiento,
                factor=linea.factor,
                precio=linea.precio,
                orden=linea.orden,
            )
        )

    mediciones = (
        await session.execute(
            select(LineaMedicion)
            .where(LineaMedicion.partida_id == partida.id)
            .order_by(LineaMedicion.orden)
        )
    ).scalars()
    for medicion in mediciones:
        session.add(
            LineaMedicion(
                organization_id=org_id,
                partida_id=nueva.id,
                formula_id=medicion.formula_id,
                formula_expresion=medicion.formula_expresion,
                formula_valores=medicion.formula_valores,
                comentario=medicion.comentario,
                uds=medicion.uds,
                longitud=medicion.longitud,
                anchura=medicion.anchura,
                altura=medicion.altura,
                parcial=medicion.parcial,
                orden=medicion.orden,
            )
        )
    return nueva


async def _clonar_capitulo(
    session: AsyncSession,
    capitulo: Capitulo,
    org_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    orden: int,
) -> Capitulo:
    """Clona un capítulo entero: subcapítulos y partidas —con su descompuesto
    y mediciones— a cualquier profundidad, todo con ids nuevos."""
    nuevo = Capitulo(
        organization_id=org_id,
        presupuesto_id=presupuesto_id,
        parent_id=parent_id,
        codigo=capitulo.codigo,
        resumen=capitulo.resumen,
        texto=capitulo.texto,
        orden=orden,
    )
    session.add(nuevo)
    await session.flush()

    partidas = (
        await session.execute(
            select(Partida).where(Partida.capitulo_id == capitulo.id).order_by(Partida.orden)
        )
    ).scalars()
    for i, partida in enumerate(partidas):
        await _clonar_partida(session, partida, org_id, presupuesto_id, nuevo.id, i)

    subcapitulos = (
        await session.execute(
            select(Capitulo).where(Capitulo.parent_id == capitulo.id).order_by(Capitulo.orden)
        )
    ).scalars()
    for i, hijo in enumerate(subcapitulos):
        await _clonar_capitulo(session, hijo, org_id, presupuesto_id, nuevo.id, i)

    return nuevo


async def _reparentar_capitulo(
    session: AsyncSession,
    capitulo: Capitulo,
    presupuesto_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    orden: int,
) -> None:
    """Reengancha un capítulo a otro punto del árbol, o a otro presupuesto."""
    capitulo.parent_id = parent_id
    capitulo.orden = orden
    if capitulo.presupuesto_id == presupuesto_id:
        return
    capitulo.presupuesto_id = presupuesto_id
    # Cruza a otro presupuesto: todo lo que cuelga de él —subcapítulos y
    # partidas, a cualquier profundidad— tiene que migrar con él. Si no, se
    # queda con un `presupuesto_id` que ya no coincide con el árbol al que
    # ahora pertenece y `cargar_estructura` (que filtra por `presupuesto_id`
    # en cada tabla) lo deja fuera de los dos presupuestos a la vez.
    nivel = [capitulo.id]
    while nivel:
        hijos = (
            await session.execute(select(Capitulo).where(Capitulo.parent_id.in_(nivel)))
        ).scalars().all()
        for hijo in hijos:
            hijo.presupuesto_id = presupuesto_id
        partidas = (
            await session.execute(select(Partida).where(Partida.capitulo_id.in_(nivel)))
        ).scalars().all()
        for partida in partidas:
            partida.presupuesto_id = presupuesto_id
        nivel = [h.id for h in hijos]


async def pegar_capitulos(
    session: AsyncSession,
    presupuesto_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    capitulo_ids: list[uuid.UUID],
    alcance: str,
) -> int:
    """Copia o mueve capítulos enteros —con todo lo que cuelguen de ellos— a
    otro punto del árbol, del mismo presupuesto o de otro (Fase 1e).

    `parent_id=None` los deja a nivel raíz del presupuesto destino."""
    org_id = require_organization_id()
    presupuesto = await obtener(session, presupuesto_id)
    if presupuesto is None:
        return 0

    if parent_id is not None:
        padre = await session.scalar(
            select(Capitulo).where(Capitulo.id == parent_id, Capitulo.organization_id == org_id)
        )
        if padre is None:
            return 0

    origen = list(
        (
            await session.execute(
                select(Capitulo).where(
                    Capitulo.id.in_(capitulo_ids), Capitulo.organization_id == org_id
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {c.id: c for c in origen}
    orden_pedido = [origen_por_id[cid] for cid in capitulo_ids if cid in origen_por_id]

    # Sin esto, colgar un capítulo de sí mismo o de uno de sus propios
    # descendientes cerraría un ciclo en el árbol.
    if parent_id is not None:
        origen_ids = {c.id for c in orden_pedido}
        cadena: uuid.UUID | None = parent_id
        vistos: set[uuid.UUID] = set()
        while cadena is not None and cadena not in vistos:
            if cadena in origen_ids:
                return 0
            vistos.add(cadena)
            ancestro = await session.get(Capitulo, cadena)
            cadena = ancestro.parent_id if ancestro else None

    siguiente = await session.scalar(
        select(func.max(Capitulo.orden)).where(
            Capitulo.presupuesto_id == presupuesto_id,
            Capitulo.parent_id.is_(None) if parent_id is None else Capitulo.parent_id == parent_id,
        )
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    afectados = 0
    for capitulo in orden_pedido:
        if capitulo.id == parent_id:
            continue
        if alcance == "mover":
            await _reparentar_capitulo(session, capitulo, presupuesto_id, parent_id, orden)
        else:
            await _clonar_capitulo(session, capitulo, org_id, presupuesto_id, parent_id, orden)
        afectados += 1
        orden += 1

    await session.flush()
    return afectados


async def pegar_lineas_medicion(
    session: AsyncSession, partida_id: uuid.UUID, linea_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve líneas de medición sueltas a otra partida."""
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(LineaMedicion).where(
                    LineaMedicion.id.in_(linea_ids), LineaMedicion.organization_id == org_id
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {l.id: l for l in origen}
    orden_pedido = [origen_por_id[lid] for lid in linea_ids if lid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(LineaMedicion.orden)).where(LineaMedicion.partida_id == partida_id)
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    partidas_origen: set[uuid.UUID] = set()
    for linea in orden_pedido:
        partidas_origen.add(linea.partida_id)
        if alcance == "mover":
            linea.partida_id = partida_id
            linea.orden = orden
        else:
            session.add(
                LineaMedicion(
                    organization_id=org_id,
                    partida_id=partida_id,
                    formula_id=linea.formula_id,
                    formula_expresion=linea.formula_expresion,
                    formula_valores=linea.formula_valores,
                    comentario=linea.comentario,
                    uds=linea.uds,
                    longitud=linea.longitud,
                    anchura=linea.anchura,
                    altura=linea.altura,
                    parcial=linea.parcial,
                    orden=orden,
                )
            )
        orden += 1
    await session.flush()

    await calc.recalcular_partida(session, partida)
    await _refrescar_venta(session, partida)
    if alcance == "mover":
        for origen_id in partidas_origen - {partida_id}:
            origen_partida = await obtener_partida(session, origen_id)
            if origen_partida is not None:
                # Si se llevó la última línea, la partida de origen se queda
                # sin desglose y `recalcular_partida` ya no toca la medición
                # (para no pisar una manual) — pero lo que había ahí era la
                # suma de unas líneas que ya no son suyas, así que aquí sí
                # hay que ponerla a cero explícitamente (mismo caso que
                # `eliminar_linea`).
                if not await _tiene_desglose(session, origen_id):
                    origen_partida.medicion = Decimal("0.000")
                await calc.recalcular_partida(session, origen_partida)
                await _refrescar_venta(session, origen_partida)
    return len(orden_pedido)


async def pegar_componentes_descompuesto(
    session: AsyncSession, partida_id: uuid.UUID, linea_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve componentes de un descompuesto a otra partida.

    Independiza la partida destino si todavía heredaba del banco, igual que
    al añadir un componente a mano — el banco no se toca."""
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(PartidaDescomposicion).where(
                    PartidaDescomposicion.id.in_(linea_ids),
                    PartidaDescomposicion.organization_id == org_id,
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {l.id: l for l in origen}
    orden_pedido = [origen_por_id[lid] for lid in linea_ids if lid in origen_por_id]

    await independizar_descomposicion(session, partida)
    siguiente = await session.scalar(
        select(func.max(PartidaDescomposicion.orden)).where(
            PartidaDescomposicion.partida_id == partida_id
        )
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    partidas_origen: set[uuid.UUID] = set()
    for linea in orden_pedido:
        partidas_origen.add(linea.partida_id)
        if alcance == "mover":
            linea.partida_id = partida_id
            linea.orden = orden
        else:
            session.add(
                PartidaDescomposicion(
                    organization_id=org_id,
                    partida_id=partida_id,
                    hijo_id=linea.hijo_id,
                    codigo=linea.codigo,
                    resumen=linea.resumen,
                    unidad=linea.unidad,
                    naturaleza=linea.naturaleza,
                    rendimiento=linea.rendimiento,
                    factor=linea.factor,
                    precio=linea.precio,
                    orden=orden,
                )
            )
        orden += 1
    await session.flush()

    await calc.recalcular_desde_descomposicion(session, partida)
    await _refrescar_venta(session, partida)
    if alcance == "mover":
        for origen_id in partidas_origen - {partida_id}:
            origen_partida = await obtener_partida(session, origen_id)
            if origen_partida is not None:
                await calc.recalcular_desde_descomposicion(session, origen_partida)
                await _refrescar_venta(session, origen_partida)
    return len(orden_pedido)


async def integrar_en_banco_precios(session: AsyncSession, partida_id: uuid.UUID) -> Partida | None:
    """Da de alta un concepto nuevo a partir de una partida alzada, y liga la
    partida a él.

    A partir de aquí la partida sigue la cascada de precios como cualquier
    otra del cuadro (mientras el presupuesto no esté bloqueado); antes de esto
    una partida alzada era un callejón sin salida, sin forma de reutilizar lo
    que llevaba tecleado en otro presupuesto.
    """
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    if partida.concepto_id is not None:
        raise ConceptoYaVinculado(
            "Esta partida ya está vinculada a un concepto del banco de precios"
        )

    org_id = require_organization_id()
    existe = await session.scalar(
        select(Concepto.id).where(
            Concepto.organization_id == org_id, Concepto.codigo == partida.codigo
        )
    )
    if existe:
        raise CodigoDuplicado(
            f"Ya existe un concepto con el código '{partida.codigo}' en el banco de precios; "
            "cambia el código de la partida antes de integrarla"
        )

    concepto = Concepto(
        organization_id=org_id,
        codigo=partida.codigo,
        tipo=TipoConcepto.UNITARIO,
        unidad=partida.unidad,
        resumen=partida.resumen,
        texto=partida.texto,
        precio=partida.precio,
        origen_precio=OrigenPrecio.MANUAL,
        **datos_autoria(),
    )
    session.add(concepto)
    await session.flush()
    await calculo.registrar_historico(session, concepto)

    partida.concepto_id = concepto.id
    await session.flush()
    return partida


# --- Fórmulas de medición (Fase 37) ---


async def listar_formulas(
    session: AsyncSession, cuenta_id: uuid.UUID, *, solo_activas: bool = False
) -> list[FormulaMedicion]:
    condiciones = [FormulaMedicion.cuenta_id == cuenta_id]
    if solo_activas:
        condiciones.append(FormulaMedicion.activa.is_(True))
    filas = await session.execute(
        select(FormulaMedicion)
        .where(*condiciones)
        .order_by(FormulaMedicion.orden, FormulaMedicion.nombre)
    )
    return list(filas.scalars())


async def crear_formula(
    session: AsyncSession, cuenta_id: uuid.UUID, datos: FormulaMedicionCreate
) -> FormulaMedicion:
    # Se valida antes de guardar: una fórmula que no se puede evaluar no sirve
    # de nada y daría error más tarde, al medir, lejos de donde se escribió.
    formulas.validar(datos.expresion)
    existe = await session.scalar(
        select(FormulaMedicion.id).where(
            FormulaMedicion.cuenta_id == cuenta_id, FormulaMedicion.nombre == datos.nombre
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya hay una fórmula llamada '{datos.nombre}'")
    formula = FormulaMedicion(cuenta_id=cuenta_id, **datos.model_dump())
    session.add(formula)
    await session.flush()
    return formula


async def actualizar_formula(
    session: AsyncSession, cuenta_id: uuid.UUID, formula_id: uuid.UUID, datos: FormulaMedicionUpdate
) -> FormulaMedicion | None:
    formula = await session.scalar(
        select(FormulaMedicion).where(
            FormulaMedicion.id == formula_id, FormulaMedicion.cuenta_id == cuenta_id
        )
    )
    if formula is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)
    if "expresion" in cambios and cambios["expresion"]:
        formulas.validar(cambios["expresion"])
    for campo, valor in cambios.items():
        setattr(formula, campo, valor)
    await session.flush()
    return formula


async def eliminar_formula(
    session: AsyncSession, cuenta_id: uuid.UUID, formula_id: uuid.UUID
) -> bool:
    formula = await session.scalar(
        select(FormulaMedicion).where(
            FormulaMedicion.id == formula_id, FormulaMedicion.cuenta_id == cuenta_id
        )
    )
    if formula is None:
        return False
    # Las líneas que la usaban conservan su copia congelada de la expresión
    # (`formula_expresion`), así que borrar el catálogo no altera mediciones ya
    # hechas: solo deja de ofrecerse para las nuevas.
    await session.delete(formula)
    await session.flush()
    return True


# --- Líneas de medición ---


async def _expresion_de(session: AsyncSession, formula_id: uuid.UUID | None) -> str | None:
    """Expresión de la fórmula elegida, para congelarla en la línea (Fase 37)."""
    if formula_id is None:
        return None
    formula = await session.scalar(
        select(FormulaMedicion).where(FormulaMedicion.id == formula_id)
    )
    if formula is None:
        raise FormulaNoEncontrada("La fórmula no existe")
    return formula.expresion


def _valores_json(valores: dict | None) -> dict[str, str]:
    """Los valores de la fórmula van a una columna JSONB, y `Decimal` no es
    serializable a JSON. Se guardan como texto —igual que viajan todos los
    decimales por la API— y el evaluador ya los convierte al calcular."""
    return {str(k): str(v) for k, v in (valores or {}).items()}


def _nueva_linea(
    org_id: uuid.UUID,
    partida_id: uuid.UUID,
    datos: LineaMedicionCreate,
    expresion: str | None = None,
) -> LineaMedicion:
    campos = datos.model_dump()
    valores = _valores_json(campos.pop("formula_valores", None))
    campos["formula_valores"] = valores
    return LineaMedicion(
        organization_id=org_id,
        partida_id=partida_id,
        formula_expresion=expresion,
        parcial=calc.parcial_de(
            datos.uds,
            datos.longitud,
            datos.anchura,
            datos.altura,
            expresion=expresion,
            valores=valores,
        ),
        **campos,
    )


async def crear_linea(
    session: AsyncSession, partida_id: uuid.UUID, datos: LineaMedicionCreate
) -> LineaMedicion | None:
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    expresion = await _expresion_de(session, datos.formula_id)
    linea = _nueva_linea(org_id, partida_id, datos, expresion)
    session.add(linea)
    await session.flush()
    await calc.recalcular_partida(session, partida)
    await _refrescar_venta(session, partida)
    return linea


async def obtener_linea(session: AsyncSession, linea_id: uuid.UUID) -> LineaMedicion | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(LineaMedicion).where(
            LineaMedicion.id == linea_id, LineaMedicion.organization_id == org_id
        )
    )


async def actualizar_linea(
    session: AsyncSession, linea_id: uuid.UUID, datos: LineaMedicionUpdate
) -> LineaMedicion | None:
    linea = await obtener_linea(session, linea_id)
    if linea is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        setattr(linea, campo, valor)

    # Cambiar de fórmula (o quitarla) rehace la copia congelada de la expresión.
    if "formula_id" in cambios:
        linea.formula_expresion = await _expresion_de(session, linea.formula_id)
    if "formula_valores" in cambios:
        linea.formula_valores = _valores_json(cambios["formula_valores"])
    if linea.formula_valores is None:
        linea.formula_valores = {}

    linea.parcial = calc.parcial_de(
        linea.uds,
        linea.longitud,
        linea.anchura,
        linea.altura,
        expresion=linea.formula_expresion,
        valores=linea.formula_valores,
    )
    await session.flush()

    partida = await obtener_partida(session, linea.partida_id)
    if partida is not None:
        await calc.recalcular_partida(session, partida)
        await _refrescar_venta(session, partida)
    return linea


async def eliminar_linea(session: AsyncSession, linea_id: uuid.UUID) -> bool:
    linea = await obtener_linea(session, linea_id)
    if linea is None:
        return False
    partida_id = linea.partida_id
    await session.delete(linea)
    await session.flush()

    partida = await obtener_partida(session, partida_id)
    if partida is not None:
        # Al quitar la última línea la partida se queda sin desglose, y
        # `recalcular_partida` ya no toca la medición para no pisar las
        # manuales: aquí sí hay que ponerla a cero explícitamente, porque lo
        # que había era la suma de unas líneas que ya no existen.
        if not await _tiene_desglose(session, partida_id):
            partida.medicion = Decimal("0.000")
        await calc.recalcular_partida(session, partida)
        await _refrescar_venta(session, partida)
    return True


class ConversionImposible(Exception):
    pass


# --- Descompuesto de la partida (Fase 34) ---


async def _lineas_heredadas(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[tuple[Descomposicion, Concepto]]:
    """Descompuesto del concepto del banco, con el hijo de cada línea."""
    filas = await session.execute(
        select(Descomposicion, Concepto)
        .join(Concepto, Concepto.id == Descomposicion.hijo_id)
        .where(Descomposicion.padre_id == concepto_id)
        .order_by(Descomposicion.orden)
    )
    return [(linea, hijo) for linea, hijo in filas.all()]


async def independizar_descomposicion(
    session: AsyncSession, partida: Partida
) -> list[PartidaDescomposicion]:
    """Clona el descompuesto del concepto en la partida, si no lo tiene ya.

    Es lo que convierte "cambiar el precio solo aquí" en algo posible: hasta
    ahora la partida compartía el descompuesto del banco con todos los demás
    presupuestos. Se copian también `costes_indirectos` para que la operación
    sea neutra en precio — independizarse no puede cambiar lo que vale la
    partida, solo de dónde sale ese valor.
    """
    org_id = require_organization_id()
    existentes = (
        await session.execute(
            select(PartidaDescomposicion)
            .where(PartidaDescomposicion.partida_id == partida.id)
            .order_by(PartidaDescomposicion.orden)
        )
    ).scalars()
    ya = list(existentes)
    if ya:
        return ya
    if partida.concepto_id is None:
        return []

    concepto = await session.scalar(
        select(Concepto).where(
            Concepto.id == partida.concepto_id, Concepto.organization_id == org_id
        )
    )
    if concepto is None:
        return []

    nuevas: list[PartidaDescomposicion] = []
    for orden, (linea, hijo) in enumerate(await _lineas_heredadas(session, concepto.id)):
        fila = PartidaDescomposicion(
            organization_id=org_id,
            partida_id=partida.id,
            hijo_id=hijo.id,
            codigo=hijo.codigo,
            resumen=hijo.resumen,
            unidad=hijo.unidad,
            naturaleza=str(hijo.naturaleza),
            rendimiento=linea.rendimiento,
            factor=linea.factor,
            precio=hijo.precio,
            orden=orden,
        )
        session.add(fila)
        nuevas.append(fila)

    if nuevas:
        partida.costes_indirectos = concepto.costes_indirectos
    await session.flush()
    return nuevas


async def descomposicion_de_partida(
    session: AsyncSession, partida_id: uuid.UUID
) -> tuple[bool, list[dict]] | None:
    """Descompuesto que se le enseña a la partida: el suyo si lo tiene, y si no
    el del banco en modo lectura. El booleano dice cuál de los dos es."""
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None

    propias = (
        await session.execute(
            select(PartidaDescomposicion)
            .where(PartidaDescomposicion.partida_id == partida.id)
            .order_by(PartidaDescomposicion.orden)
        )
    ).scalars()
    propias = list(propias)
    if propias:
        return True, [
            {
                "id": f.id,
                "hijo_id": f.hijo_id,
                "codigo": f.codigo,
                "resumen": f.resumen,
                "unidad": f.unidad,
                "naturaleza": f.naturaleza,
                "rendimiento": f.rendimiento,
                "factor": f.factor,
                "precio": f.precio,
                "importe": redondear_precio(f.rendimiento * f.factor * f.precio),
            }
            for f in propias
        ]

    if partida.concepto_id is None:
        return False, []
    return False, [
        {
            "id": linea.id,
            "hijo_id": hijo.id,
            "codigo": hijo.codigo,
            "resumen": hijo.resumen,
            "unidad": hijo.unidad,
            "naturaleza": hijo.naturaleza,
            "rendimiento": linea.rendimiento,
            "factor": linea.factor,
            "precio": hijo.precio,
            "importe": redondear_precio(linea.rendimiento * linea.factor * hijo.precio),
        }
        for linea, hijo in await _lineas_heredadas(session, partida.concepto_id)
    ]


async def anadir_componente(
    session: AsyncSession,
    partida_id: uuid.UUID,
    hijo_id: uuid.UUID,
    rendimiento: Decimal,
    factor: Decimal,
) -> bool:
    """Añade un componente al descompuesto de la partida (Fase 34).

    Si la partida todavía heredaba el descompuesto del banco, primero se
    independiza: añadir una línea "solo aquí" es exactamente el caso que la
    descomposición propia existe para resolver. Una partida alzada (sin
    concepto) arranca con un descompuesto vacío y este es su primer componente.
    """
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False

    hijo = await session.scalar(
        select(Concepto).where(Concepto.id == hijo_id, Concepto.organization_id == org_id)
    )
    if hijo is None:
        raise ConceptoInvalido("El concepto no existe en esta organización")

    await independizar_descomposicion(session, partida)
    siguiente = await session.scalar(
        select(func.count())
        .select_from(PartidaDescomposicion)
        .where(PartidaDescomposicion.partida_id == partida.id)
    )
    session.add(
        PartidaDescomposicion(
            organization_id=org_id,
            partida_id=partida.id,
            hijo_id=hijo.id,
            codigo=hijo.codigo,
            resumen=hijo.resumen,
            unidad=hijo.unidad,
            naturaleza=str(hijo.naturaleza),
            rendimiento=rendimiento,
            factor=factor,
            precio=hijo.precio,
            orden=int(siguiente or 0),
        )
    )
    await session.flush()
    await calc.recalcular_desde_descomposicion(session, partida)
    await _refrescar_venta(session, partida)
    return True


async def quitar_componente(
    session: AsyncSession, partida_id: uuid.UUID, linea_id: uuid.UUID
) -> bool:
    """Quita una línea del descompuesto propio de la partida."""
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    linea = await session.scalar(
        select(PartidaDescomposicion).where(
            PartidaDescomposicion.id == linea_id,
            PartidaDescomposicion.partida_id == partida_id,
            PartidaDescomposicion.organization_id == org_id,
        )
    )
    if linea is None:
        return False
    await session.delete(linea)
    await session.flush()
    # Si era la última, la partida se queda con descompuesto vacío: el precio
    # deja de calcularse y se queda con el que tuviera, que es lo mismo que le
    # pasa a una partida alzada.
    await calc.recalcular_desde_descomposicion(session, partida)
    await _refrescar_venta(session, partida)
    return True


async def cambiar_precio_componente(
    session: AsyncSession,
    partida_id: uuid.UUID,
    hijo_id: uuid.UUID,
    precio: Decimal,
    alcance: str,
) -> int:
    """Cambia el precio de un componente del descompuesto (Fase 34).

    Con alcance `partida` afecta solo a esa; con `presupuesto`, a todas las del
    mismo presupuesto que lleven ese componente. En ambos casos las partidas
    afectadas se independizan del banco: el banco de precios no se toca nunca
    desde aquí, porque cambiarlo arrastraría a otros presupuestos que el
    usuario no está mirando.

    Devuelve cuántas partidas se han visto afectadas.
    """
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return 0

    objetivo = [partida]
    if alcance == "presupuesto":
        org_id = require_organization_id()
        hermanas = (
            await session.execute(
                select(Partida)
                .options(selectinload(Partida.lineas))
                .where(
                    Partida.presupuesto_id == partida.presupuesto_id,
                    Partida.organization_id == org_id,
                    Partida.id != partida.id,
                )
            )
        ).scalars()
        objetivo.extend(hermanas)

    afectadas = 0
    for candidata in objetivo:
        lineas = await independizar_descomposicion(session, candidata)
        tocada = False
        for linea in lineas:
            if linea.hijo_id == hijo_id:
                linea.precio = redondear_precio(precio)
                tocada = True
        if not tocada:
            continue
        await session.flush()
        await calc.recalcular_desde_descomposicion(session, candidata)
        await _refrescar_venta(session, candidata)
        afectadas += 1

    return afectadas


async def cambiar_rendimiento_componente(
    session: AsyncSession, partida_id: uuid.UUID, hijo_id: uuid.UUID, rendimiento: Decimal
) -> bool:
    """Cambia el rendimiento de un componente del descompuesto de la partida.

    A diferencia del precio, el rendimiento no se comparte nunca entre
    partidas —es cuánto gasta ESTA partida de ese componente por unidad—, así
    que no hay alcance que elegir: siempre es "solo aquí". Si la partida
    todavía heredaba el descompuesto del banco, se independiza igual que al
    tocar el precio, porque el banco no se toca desde aquí.
    """
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    lineas = await independizar_descomposicion(session, partida)
    tocada = False
    for linea in lineas:
        if linea.hijo_id == hijo_id:
            linea.rendimiento = rendimiento
            tocada = True
    if not tocada:
        return False
    await session.flush()
    await calc.recalcular_desde_descomposicion(session, partida)
    await _refrescar_venta(session, partida)
    return True


async def cambiar_resumen_componente(
    session: AsyncSession, partida_id: uuid.UUID, hijo_id: uuid.UUID, resumen: str
) -> bool:
    """Cambia el texto de un componente del descompuesto (Fase 38).

    Igual que el rendimiento: no afecta al precio, así que no hace falta
    recalcular nada, solo independizar si la partida todavía heredaba del
    banco. El concepto del banco tampoco se toca — es la etiqueta que se ve
    en ESTE descompuesto, no un renombrado global."""
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    lineas = await independizar_descomposicion(session, partida)
    tocada = False
    for linea in lineas:
        if linea.hijo_id == hijo_id:
            linea.resumen = resumen
            tocada = True
    if not tocada:
        return False
    await session.flush()
    return True


async def cambiar_unidad_componente(
    session: AsyncSession, partida_id: uuid.UUID, hijo_id: uuid.UUID, unidad: str
) -> bool:
    """Cambia la unidad de un componente ya en el descompuesto (Fase 38) —
    para corregir, por ejemplo, una mano de obra que se dio de alta en "ud"
    en vez de en "h", y que por eso no contaba en las horas presupuestadas."""
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    lineas = await independizar_descomposicion(session, partida)
    tocada = False
    for linea in lineas:
        if linea.hijo_id == hijo_id:
            linea.unidad = unidad
            tocada = True
    if not tocada:
        return False
    await session.flush()
    return True


async def cambiar_naturaleza_componente(
    session: AsyncSession, partida_id: uuid.UUID, hijo_id: uuid.UUID, naturaleza: str
) -> bool:
    """Cambia la clasificación (material/mano de obra/...) de un componente
    ya en el descompuesto (Fase 38) — para corregir líneas que se quedaron
    "sin clasificar" de antes de que se pudiera elegir al crearlas."""
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    lineas = await independizar_descomposicion(session, partida)
    tocada = False
    for linea in lineas:
        if linea.hijo_id == hijo_id:
            linea.naturaleza = naturaleza
            tocada = True
    if not tocada:
        return False
    await session.flush()
    return True


async def convertir_linea(
    session: AsyncSession, linea_id: uuid.UUID, tipo_destino: str
) -> tuple[str, uuid.UUID] | None:
    """Convierte un capítulo en partida o al revés (Fase 33).

    Al teclear un presupuesto seguido, se crea la línea antes de saber qué va a
    ser; poder cambiarlo desde la propia celda de tipo evita tener que borrar y
    rehacer. Solo se permite sobre líneas "vacías" —un capítulo sin nada dentro,
    una partida sin desglose de medición—, porque en cualquier otro caso habría
    que decidir qué pasa con el contenido, y eso es una decisión del usuario,
    no de un `convert`.

    Devuelve (tipo_nuevo, id_nuevo); la línea original desaparece.
    """
    org_id = require_organization_id()

    capitulo = await session.scalar(
        select(Capitulo).where(Capitulo.id == linea_id, Capitulo.organization_id == org_id)
    )
    if capitulo is not None:
        if tipo_destino == "capitulo":
            return ("capitulo", capitulo.id)
        if capitulo.parent_id is None:
            raise ConversionImposible(
                "Un capítulo de primer nivel no puede ser una partida: no hay capítulo que la contenga"
            )
        hijos = await session.scalar(
            select(func.count()).select_from(Capitulo).where(Capitulo.parent_id == capitulo.id)
        )
        partidas = await session.scalar(
            select(func.count()).select_from(Partida).where(Partida.capitulo_id == capitulo.id)
        )
        if (hijos or 0) > 0 or (partidas or 0) > 0:
            raise ConversionImposible("El capítulo tiene contenido; vacíalo antes de convertirlo")

        partida = Partida(
            organization_id=org_id,
            presupuesto_id=capitulo.presupuesto_id,
            capitulo_id=capitulo.parent_id,
            concepto_id=None,
            codigo=capitulo.codigo,
            resumen=capitulo.resumen,
            texto=capitulo.texto,
            unidad="ud",
            precio=Decimal("0.00"),
            orden=capitulo.orden,
        )
        session.add(partida)
        await session.delete(capitulo)
        await session.flush()
        return ("partida", partida.id)

    partida = await session.scalar(
        select(Partida)
        .options(selectinload(Partida.lineas))
        .where(Partida.id == linea_id, Partida.organization_id == org_id)
    )
    if partida is None:
        return None
    if tipo_destino == "partida":
        return ("partida", partida.id)
    if partida.lineas:
        raise ConversionImposible(
            "La partida tiene líneas de medición; bórralas antes de convertirla en capítulo"
        )

    capitulo_nuevo = Capitulo(
        organization_id=org_id,
        presupuesto_id=partida.presupuesto_id,
        parent_id=partida.capitulo_id,
        codigo=partida.codigo,
        resumen=partida.resumen,
        texto=partida.texto,
        orden=partida.orden,
    )
    session.add(capitulo_nuevo)
    await session.delete(partida)
    await session.flush()
    return ("capitulo", capitulo_nuevo.id)


# --- Reajuste del presupuesto (Fase 36) ---


class ReajusteImposible(Exception):
    pass


async def reajustar(
    session: AsyncSession,
    presupuesto_id: uuid.UUID,
    tipo: str,
    valor: Decimal,
    aplicar: bool,
) -> dict | None:
    """Lleva el presupuesto a un importe o a un margen objetivo (Fase 36).

    No escala cada precio de venta por su cuenta: despeja el ÚNICO porcentaje
    del método del presupuesto que, aplicado por igual a todas las partidas
    sin bloquear, deja la venta conjunta en el objetivo. Es lo mismo que hacer
    a mano "sube el %GG+%BI" o "sube el %incremento" hasta cuadrar, pero sin
    tanteo — y el resultado queda igual de "fijo" y consistente que si se
    hubiera tecleado ese porcentaje en la cabecera del presupuesto.

    Cada método traduce el objetivo a su propio porcentaje: incremento sobre
    coste y el clásico (%GG+%BI) comparten fórmula —son un recargo sobre el
    coste—, así que se despeja igual y para el clásico se reparte el recargo
    entre GG y BI a prorrata de como estaban. Beneficio final es distinto
    porque su porcentaje no es un recargo sobre el coste sino el margen sobre
    la propia venta, así que hace falta un paso más de conversión.

    Solo se mueven las partidas con la venta SIN bloquear: las bloqueadas son
    precios pactados y el reajuste tiene que respetarlos, así que el resto
    absorbe toda la diferencia.

    Con `aplicar=False` no toca nada: devuelve exactamente el mismo cálculo
    para poder enseñarlo antes de decidir.
    """
    presupuesto = await obtener(session, presupuesto_id)
    if presupuesto is None:
        return None

    org_id = require_organization_id()
    partidas = list(
        (
            await session.execute(
                select(Partida)
                .where(
                    Partida.presupuesto_id == presupuesto_id,
                    Partida.organization_id == org_id,
                )
                .order_by(Partida.orden)
            )
        ).scalars()
    )
    if not partidas:
        raise ReajusteImposible("El presupuesto no tiene partidas que reajustar")

    coste = redondear_precio(sum((p.importe for p in partidas), Decimal("0.00")))
    venta_antes = redondear_precio(sum((p.importe_venta for p in partidas), Decimal("0.00")))

    if tipo == "margen":
        if valor >= Decimal("100"):
            raise ReajusteImposible(
                "Un margen del 100 % o más no tiene solución: el coste nunca llegaría a cubrirse"
            )
        objetivo = redondear_precio(coste / (Decimal("1") - valor / Decimal("100")))
    else:
        objetivo = redondear_precio(valor)

    libres = [p for p in partidas if not p.venta_bloqueada]
    bloqueadas = [p for p in partidas if p.venta_bloqueada]
    if not libres:
        raise ReajusteImposible(
            "Todas las ventas están bloqueadas: quita algún candado para poder reajustar"
        )

    venta_bloqueada = redondear_precio(sum((p.importe_venta for p in bloqueadas), Decimal("0.00")))
    objetivo_libre = objetivo - venta_bloqueada
    if objetivo_libre < 0:
        raise ReajusteImposible(
            f"Las ventas bloqueadas suman {venta_bloqueada} €, ya por encima del objetivo de {objetivo} €"
        )

    coste_libre = redondear_precio(sum((p.importe for p in libres), Decimal("0.00")))
    if coste_libre <= 0:
        raise ReajusteImposible(
            "Las partidas a reajustar no tienen coste: no hay ningún porcentaje que aplicar"
        )

    metodo, porcentaje_actual = calc.metodo_de(presupuesto)
    if metodo == MetodoCalculo.CLASICO:
        porcentaje_anterior = presupuesto.gastos_generales + presupuesto.beneficio_industrial
    else:
        porcentaje_anterior = porcentaje_actual

    try:
        porcentaje_nuevo, gg_nuevo, bi_nuevo = calc.resolver_porcentaje_objetivo(
            metodo,
            presupuesto.gastos_generales,
            presupuesto.beneficio_industrial,
            coste_libre,
            objetivo_libre,
        )
    except calc.PorcentajeImposible as exc:
        raise ReajusteImposible(str(exc)) from exc

    def venta_de(coste_partida: Decimal) -> Decimal:
        if metodo == MetodoCalculo.BENEFICIO_FINAL:
            return calc.venta_unitaria(coste_partida, metodo, porcentaje_nuevo)
        # El clásico no lo resuelve `venta_unitaria` (necesita el GG+BI del
        # presupuesto, no un único porcentaje), pero su fórmula es idéntica a
        # la de incremento sobre coste una vez que se tiene el recargo
        # combinado, así que se reutiliza esa rama.
        return calc.venta_unitaria(coste_partida, MetodoCalculo.INCREMENTO_SOBRE_COSTE, porcentaje_nuevo)

    lineas = []
    bajo_coste = 0
    for partida in partidas:
        if partida.venta_bloqueada:
            nueva_venta = partida.precio_venta
            nuevo_importe = partida.importe_venta
        else:
            nueva_venta = venta_de(partida.precio)
            nuevo_importe = redondear_precio(partida.medicion * nueva_venta)
            if nueva_venta < partida.precio:
                bajo_coste += 1
        lineas.append(
            {
                "partida_id": partida.id,
                "codigo": partida.codigo,
                "resumen": partida.resumen,
                "bloqueada": partida.venta_bloqueada,
                "coste": partida.precio,
                "venta_antes": partida.precio_venta,
                "venta_despues": nueva_venta,
                "importe_antes": partida.importe_venta,
                "importe_despues": nuevo_importe,
            }
        )

    venta_despues = redondear_precio(
        sum((linea["importe_despues"] for linea in lineas), Decimal("0.00"))
    )

    if aplicar:
        if metodo == MetodoCalculo.CLASICO:
            presupuesto.gastos_generales = gg_nuevo
            presupuesto.beneficio_industrial = bi_nuevo
        else:
            presupuesto.porcentaje_metodo = porcentaje_nuevo
        for partida, linea in zip(partidas, lineas, strict=True):
            if partida.venta_bloqueada:
                continue
            partida.precio_venta = linea["venta_despues"]
            partida.importe_venta = linea["importe_despues"]
        await session.flush()

    def margen_pct(venta: Decimal) -> Decimal:
        return redondear_precio((venta - coste) * Decimal("100") / venta) if venta else Decimal("0.00")

    return {
        "aplicado": aplicar,
        "metodo": metodo,
        "objetivo_venta": objetivo,
        "coste": coste,
        "venta_antes": venta_antes,
        "venta_despues": venta_despues,
        "diferencia": venta_despues - objetivo,
        "margen_antes": margen_pct(venta_antes),
        "margen_despues": margen_pct(venta_despues),
        "porcentaje_anterior": porcentaje_anterior,
        "porcentaje_nuevo": porcentaje_nuevo,
        "partidas_afectadas": len(libres),
        "partidas_bloqueadas": len(bloqueadas),
        "partidas_bajo_coste": bajo_coste,
        "lineas": lineas,
    }


# --- Edición por lotes (Fase 33) ---


async def actualizar_lineas_en_lote(
    session: AsyncSession, presupuesto_id: uuid.UUID, cambios: list[CambioLinea]
) -> int:
    """Aplica de golpe varios cambios de celda de la rejilla.

    Todo en la misma transacción: o entra la tanda entera o no entra nada, que
    es lo que espera quien está tecleando deprisa y no está mirando si cada
    celda ha ido bien. Devuelve cuántas líneas se han tocado de verdad.

    No llama a `recalcular_partida`: la medición solo cambia si cambian las
    líneas de medición, y aquí no se tocan. Basta con rehacer el importe, que
    además evita una consulta por fila.
    """
    org_id = require_organization_id()
    presupuesto = await obtener(session, presupuesto_id)
    aplicados = 0

    for cambio in cambios:
        campos = cambio.model_dump(exclude_unset=True, exclude={"id", "tipo"})
        if not campos:
            continue

        if cambio.tipo == "capitulo":
            capitulo = await session.scalar(
                select(Capitulo).where(
                    Capitulo.id == cambio.id,
                    Capitulo.presupuesto_id == presupuesto_id,
                    Capitulo.organization_id == org_id,
                )
            )
            if capitulo is None:
                continue
            # Un capítulo no tiene unidad, ni precio, ni medición propios.
            for campo in ("codigo", "resumen", "texto"):
                if campo in campos:
                    setattr(capitulo, campo, campos[campo])
            aplicados += 1
            continue

        partida = await session.scalar(
            select(Partida)
            .options(selectinload(Partida.lineas))
            .where(
                Partida.id == cambio.id,
                Partida.presupuesto_id == presupuesto_id,
                Partida.organization_id == org_id,
            )
        )
        if partida is None:
            continue

        medicion_manual = campos.pop("medicion", None)
        for campo, valor in campos.items():
            setattr(partida, campo, valor)
        if "precio" in campos:
            partida.precio = redondear_precio(partida.precio)
        # Misma regla que `actualizar_partida`: con desglose manda la suma de
        # los parciales, no lo que venga escrito en la celda.
        if medicion_manual is not None and not await _tiene_desglose(session, partida.id):
            partida.medicion = redondear_medicion(medicion_manual)
        partida.importe = redondear_precio(partida.medicion * partida.precio)
        if presupuesto is not None:
            calc.aplicar_venta(presupuesto, partida)
        aplicados += 1

    await session.flush()
    return aplicados


# --- Árbol y totales ---


async def arbol_y_totales(
    session: AsyncSession, presupuesto: Presupuesto
) -> tuple[list[NodoCapitulo], TotalesOut]:
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto.id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
    acumulado_venta = calc.importes_por_capitulo(
        capitulos, partidas, campo=lambda p: p.importe_venta
    )
    pem = calc.pem_de(capitulos, acumulado)

    # Qué partidas tienen desglose de medición: una sola consulta para todo el
    # árbol, en vez de cargar las líneas de cada partida para contarlas.
    con_desglose: set[uuid.UUID] = set()
    if partidas:
        filas = await session.execute(
            select(LineaMedicion.partida_id)
            .where(LineaMedicion.partida_id.in_([p.id for p in partidas]))
            .distinct()
        )
        con_desglose = set(filas.scalars())

    # Igual para las que se han independizado del banco (Fase 34).
    independizadas: set[uuid.UUID] = set()
    if partidas:
        filas = await session.execute(
            select(PartidaDescomposicion.partida_id)
            .where(PartidaDescomposicion.partida_id.in_([p.id for p in partidas]))
            .distinct()
        )
        independizadas = set(filas.scalars())

    por_capitulo: dict[uuid.UUID, list[Partida]] = {}
    for partida in partidas:
        por_capitulo.setdefault(partida.capitulo_id, []).append(partida)

    hijos: dict[uuid.UUID | None, list[Capitulo]] = {}
    for capitulo in capitulos:
        hijos.setdefault(capitulo.parent_id, []).append(capitulo)

    def salida(partida: Partida) -> PartidaOut:
        fila = PartidaOut.model_validate(partida)
        fila.tiene_desglose = partida.id in con_desglose
        fila.descomposicion_propia = partida.id in independizadas
        # Semáforo (Fase 35): se compara la venta real con la que tocaría por
        # el método, para distinguir "va a pérdida" de "gana menos de lo
        # previsto", que no es lo mismo aunque las dos merezcan un aviso.
        objetivo = calc.venta_de_presupuesto(presupuesto, partida.precio)
        fila.estado_venta = calc.estado_venta(partida.precio, partida.precio_venta, objetivo)
        return fila

    def nodo(capitulo: Capitulo) -> NodoCapitulo:
        return NodoCapitulo(
            id=capitulo.id,
            codigo=capitulo.codigo,
            resumen=capitulo.resumen,
            texto=capitulo.texto,
            orden=capitulo.orden,
            importe=acumulado[capitulo.id],
            importe_venta=acumulado_venta[capitulo.id],
            partidas=[salida(p) for p in por_capitulo.get(capitulo.id, [])],
            hijos=[nodo(h) for h in hijos.get(capitulo.id, [])],
        )

    raices = [nodo(c) for c in hijos.get(None, [])]
    totales = TotalesOut(
        **calc.Totales(presupuesto, pem, calc.venta_total(partidas)).como_dict()
    )
    return raices, totales


async def total_de(session: AsyncSession, presupuesto: Presupuesto) -> tuple[Decimal, Decimal]:
    """(PEM, total con IVA). Para las filas del listado, sin montar el árbol."""
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto.id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
    pem = calc.pem_de(capitulos, acumulado)
    return pem, calc.Totales(presupuesto, pem, calc.venta_total(partidas)).total


# Unidad de horas del diccionario `unidad_medida` (ver migración de Fase 20)
# — es una convención de texto, no un enum: `Concepto.unidad` es libre.
_UNIDAD_HORAS = "h"


async def recursos(session: AsyncSession, presupuesto_id: uuid.UUID) -> RecursosPresupuesto:
    """Materiales y mano de obra agregados de todo el presupuesto (Fase 31),
    para los widgets "Precios básicos" y "Recursos humanos" — ver
    `presupuesto_calculo.explosion_recursos`."""
    pares = await calc.explosion_recursos(session, presupuesto_id)

    def recurso(concepto: Concepto, cantidad: Decimal, unidad_propia: str | None) -> RecursoAgregado:
        cantidad_r = redondear_medicion(cantidad)
        unidad = unidad_propia or concepto.unidad
        return RecursoAgregado(
            concepto_id=concepto.id,
            codigo=concepto.codigo,
            resumen=concepto.resumen,
            unidad=unidad,
            cantidad=cantidad_r,
            precio=concepto.precio,
            importe=redondear_precio(cantidad_r * concepto.precio),
        )

    # Si alguna partida corrigió el componente "solo aquí" (Fase 38), esa
    # naturaleza/unidad congeladas mandan sobre las del concepto del banco —
    # son las que el usuario acaba de arreglar a mano precisamente para que
    # cuenten bien aquí.
    def naturaleza_de(concepto: Concepto, propia: str | None) -> str:
        return propia or concepto.naturaleza

    def unidad_de(concepto: Concepto, propia: str | None) -> str:
        return propia or concepto.unidad

    materiales = [
        recurso(c, cantidad, u_propia)
        for c, cantidad, n_propia, u_propia in pares
        if naturaleza_de(c, n_propia) == NaturalezaConcepto.MATERIAL
    ]
    mano_obra = [
        recurso(c, cantidad, u_propia)
        for c, cantidad, n_propia, u_propia in pares
        if naturaleza_de(c, n_propia) == NaturalezaConcepto.MANO_OBRA
    ]
    horas_totales = redondear_medicion(
        sum(
            (
                cantidad
                for c, cantidad, n_propia, u_propia in pares
                if naturaleza_de(c, n_propia) == NaturalezaConcepto.MANO_OBRA
                and unidad_de(c, u_propia) == _UNIDAD_HORAS
            ),
            Decimal("0"),
        )
    )
    return RecursosPresupuesto(materiales=materiales, mano_obra=mano_obra, horas_totales=horas_totales)
