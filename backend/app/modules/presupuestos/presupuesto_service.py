import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.numeracion import siguiente_referencia
from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.presupuestos import calculo
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos.models import Concepto, NaturalezaConcepto, OrigenPrecio, TipoConcepto
from app.modules.presupuestos.models_presupuesto import (
    ESTADOS_BLOQUEADOS,
    Capitulo,
    EstadoPresupuesto,
    LineaMedicion,
    Partida,
    Presupuesto,
)
from app.modules.presupuestos.presupuesto_schemas import (
    CambioLinea,
    CapituloCreate,
    CapituloUpdate,
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
    sin_desglose = len(partida.lineas) == 0

    for campo, valor in cambios.items():
        setattr(partida, campo, valor)
    if "precio" in cambios:
        partida.precio = redondear_precio(partida.precio)

    if medicion_manual is not None and sin_desglose:
        partida.medicion = redondear_medicion(medicion_manual)
        partida.importe = redondear_precio(partida.medicion * partida.precio)
        await session.flush()
        return partida

    await session.flush()
    await calc.recalcular_partida(session, partida)
    return partida


async def eliminar_partida(session: AsyncSession, partida_id: uuid.UUID) -> bool:
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    await session.delete(partida)
    await session.flush()
    return True


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


# --- Líneas de medición ---


def _nueva_linea(
    org_id: uuid.UUID, partida_id: uuid.UUID, datos: LineaMedicionCreate
) -> LineaMedicion:
    return LineaMedicion(
        organization_id=org_id,
        partida_id=partida_id,
        parcial=calc.parcial_de(datos.uds, datos.longitud, datos.anchura, datos.altura),
        **datos.model_dump(),
    )


async def crear_linea(
    session: AsyncSession, partida_id: uuid.UUID, datos: LineaMedicionCreate
) -> LineaMedicion | None:
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    linea = _nueva_linea(org_id, partida_id, datos)
    session.add(linea)
    await session.flush()
    await calc.recalcular_partida(session, partida)
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
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(linea, campo, valor)
    linea.parcial = calc.parcial_de(linea.uds, linea.longitud, linea.anchura, linea.altura)
    await session.flush()

    partida = await obtener_partida(session, linea.partida_id)
    if partida is not None:
        await calc.recalcular_partida(session, partida)
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
        await calc.recalcular_partida(session, partida)
    return True


class ConversionImposible(Exception):
    pass


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
        if medicion_manual is not None and not partida.lineas:
            partida.medicion = redondear_medicion(medicion_manual)
        partida.importe = redondear_precio(partida.medicion * partida.precio)
        aplicados += 1

    await session.flush()
    return aplicados


# --- Árbol y totales ---


async def arbol_y_totales(
    session: AsyncSession, presupuesto: Presupuesto
) -> tuple[list[NodoCapitulo], TotalesOut]:
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto.id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
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

    por_capitulo: dict[uuid.UUID, list[Partida]] = {}
    for partida in partidas:
        por_capitulo.setdefault(partida.capitulo_id, []).append(partida)

    hijos: dict[uuid.UUID | None, list[Capitulo]] = {}
    for capitulo in capitulos:
        hijos.setdefault(capitulo.parent_id, []).append(capitulo)

    def salida(partida: Partida) -> PartidaOut:
        fila = PartidaOut.model_validate(partida)
        fila.tiene_desglose = partida.id in con_desglose
        return fila

    def nodo(capitulo: Capitulo) -> NodoCapitulo:
        return NodoCapitulo(
            id=capitulo.id,
            codigo=capitulo.codigo,
            resumen=capitulo.resumen,
            texto=capitulo.texto,
            orden=capitulo.orden,
            importe=acumulado[capitulo.id],
            partidas=[salida(p) for p in por_capitulo.get(capitulo.id, [])],
            hijos=[nodo(h) for h in hijos.get(capitulo.id, [])],
        )

    raices = [nodo(c) for c in hijos.get(None, [])]
    totales = TotalesOut(**calc.Totales(presupuesto, pem).como_dict())
    return raices, totales


async def total_de(session: AsyncSession, presupuesto: Presupuesto) -> tuple[Decimal, Decimal]:
    """(PEM, total con IVA). Para las filas del listado, sin montar el árbol."""
    capitulos, partidas = await calc.cargar_estructura(session, presupuesto.id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
    pem = calc.pem_de(capitulos, acumulado)
    return pem, calc.Totales(presupuesto, pem).total


# Unidad de horas del diccionario `unidad_medida` (ver migración de Fase 20)
# — es una convención de texto, no un enum: `Concepto.unidad` es libre.
_UNIDAD_HORAS = "h"


async def recursos(session: AsyncSession, presupuesto_id: uuid.UUID) -> RecursosPresupuesto:
    """Materiales y mano de obra agregados de todo el presupuesto (Fase 31),
    para los widgets "Precios básicos" y "Recursos humanos" — ver
    `presupuesto_calculo.explosion_recursos`."""
    pares = await calc.explosion_recursos(session, presupuesto_id)

    def recurso(concepto: Concepto, cantidad: Decimal) -> RecursoAgregado:
        cantidad_r = redondear_medicion(cantidad)
        return RecursoAgregado(
            concepto_id=concepto.id,
            codigo=concepto.codigo,
            resumen=concepto.resumen,
            unidad=concepto.unidad,
            cantidad=cantidad_r,
            precio=concepto.precio,
            importe=redondear_precio(cantidad_r * concepto.precio),
        )

    materiales = [
        recurso(c, cantidad) for c, cantidad in pares if c.naturaleza == NaturalezaConcepto.MATERIAL
    ]
    mano_obra = [
        recurso(c, cantidad) for c, cantidad in pares if c.naturaleza == NaturalezaConcepto.MANO_OBRA
    ]
    horas_totales = redondear_medicion(
        sum(
            (cantidad for c, cantidad in pares if c.naturaleza == NaturalezaConcepto.MANO_OBRA and c.unidad == _UNIDAD_HORAS),
            Decimal("0"),
        )
    )
    return RecursosPresupuesto(materiales=materiales, mano_obra=mano_obra, horas_totales=horas_totales)
