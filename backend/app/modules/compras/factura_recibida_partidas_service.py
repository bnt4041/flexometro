"""Capítulos, partidas y mediciones de la Factura recibida (de proveedor,
Fase 2). Calcado de `presupuestos.presupuesto_service`, muy simplificado: sin
descompuesto (no existe tabla `factura_recibida_partida_descomposicion`, no
aplica nunca — la factura recibida es siempre de proveedor) y sin venta
(`precio` es directamente el coste final del proveedor, no hay
`precio_venta`/`venta_bloqueada`/`importe_venta` en `FacturaRecibidaPartida`).

Tras cualquier alta/baja/edición de partida o medición se recalcula
`FacturaRecibida.base_imponible` (suma de `importe` de sus partidas) y, con
ella, `cuota_iva`/`total` — reutilizando `cuota_de` de
`factura_recibida_service.py` (la misma fórmula que usa `crear()`). Igual que
en `Factura` de venta: SOLO si la factura ya tiene alguna partida; sin
ninguna, se respeta lo tecleado a mano.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.compras.factura_recibida_partidas_schemas import (
    FacturaRecibidaCapituloCreate,
    FacturaRecibidaCapituloUpdate,
    FacturaRecibidaMedicionCreate,
    FacturaRecibidaMedicionUpdate,
    FacturaRecibidaPartidaCreate,
    FacturaRecibidaPartidaUpdate,
)
from app.modules.compras.factura_recibida_service import cuota_de
from app.modules.compras.models import (
    FacturaRecibida,
    FacturaRecibidaCapitulo,
    FacturaRecibidaMedicion,
    FacturaRecibidaPartida,
)
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos.models import Concepto


class ConceptoInvalido(Exception):
    pass


class PartidaSinDatos(Exception):
    pass


# --- Total de la factura ---


async def _recalcular_totales_factura(session: AsyncSession, factura_id: uuid.UUID) -> None:
    factura = await session.get(FacturaRecibida, factura_id)
    if factura is None:
        return
    tiene_partidas = await session.scalar(
        select(func.count())
        .select_from(FacturaRecibidaPartida)
        .where(FacturaRecibidaPartida.factura_id == factura_id)
    )
    if not tiene_partidas:
        return
    suma = await session.scalar(
        select(func.coalesce(func.sum(FacturaRecibidaPartida.importe), 0)).where(
            FacturaRecibidaPartida.factura_id == factura_id
        )
    )
    factura.base_imponible = redondear_precio(Decimal(suma))
    factura.cuota_iva = cuota_de(
        factura.base_imponible, factura.tipo_iva, factura.inversion_sujeto_pasivo
    )
    factura.total = redondear_precio(factura.base_imponible + factura.cuota_iva)
    await session.flush()


# --- Capítulos ---


async def _siguiente_codigo_capitulo(session: AsyncSession, factura_id: uuid.UUID) -> str:
    hermanos = (
        await session.execute(
            select(FacturaRecibidaCapitulo.codigo).where(
                FacturaRecibidaCapitulo.factura_id == factura_id
            )
        )
    ).scalars()
    maximo = 0
    for codigo in hermanos:
        ultimo = codigo.rsplit(".", 1)[-1]
        if ultimo.isdigit():
            maximo = max(maximo, int(ultimo))
    return f"{maximo + 1:02d}"


async def obtener_capitulo(
    session: AsyncSession, capitulo_id: uuid.UUID
) -> FacturaRecibidaCapitulo | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(FacturaRecibidaCapitulo).where(
            FacturaRecibidaCapitulo.id == capitulo_id,
            FacturaRecibidaCapitulo.organization_id == org_id,
        )
    )


async def cargar_capitulos(
    session: AsyncSession, factura_id: uuid.UUID
) -> list[FacturaRecibidaCapitulo]:
    """El árbol completo de la factura recibida, ya anidado, con mediciones
    cargadas de un tirón. `tiene_desglose` no es columna: se calcula aquí a
    partir de la relación ya cargada (mismo criterio que `pedido_service.
    cargar_capitulos`). Sin descomposición — no existe para esta entidad."""
    org_id = require_organization_id()
    capitulos = (
        await session.execute(
            select(FacturaRecibidaCapitulo)
            .where(
                FacturaRecibidaCapitulo.factura_id == factura_id,
                FacturaRecibidaCapitulo.organization_id == org_id,
            )
            .options(
                selectinload(FacturaRecibidaCapitulo.partidas).selectinload(
                    FacturaRecibidaPartida.mediciones
                )
            )
            .order_by(FacturaRecibidaCapitulo.orden, FacturaRecibidaCapitulo.codigo)
        )
    ).scalars()
    resultado = list(capitulos)
    for capitulo in resultado:
        for partida in capitulo.partidas:
            partida.tiene_desglose = len(partida.mediciones) > 0
    return resultado


async def crear_capitulo(
    session: AsyncSession, factura_id: uuid.UUID, datos: FacturaRecibidaCapituloCreate
) -> FacturaRecibidaCapitulo | None:
    org_id = require_organization_id()
    factura = await session.scalar(
        select(FacturaRecibida).where(
            FacturaRecibida.id == factura_id, FacturaRecibida.organization_id == org_id
        )
    )
    if factura is None:
        return None
    codigo = datos.codigo or await _siguiente_codigo_capitulo(session, factura_id)
    capitulo = FacturaRecibidaCapitulo(
        organization_id=org_id,
        factura_id=factura_id,
        codigo=codigo,
        resumen=datos.resumen,
        texto=datos.texto,
        orden=datos.orden,
    )
    session.add(capitulo)
    await session.flush()
    return capitulo


async def actualizar_capitulo(
    session: AsyncSession, capitulo_id: uuid.UUID, datos: FacturaRecibidaCapituloUpdate
) -> FacturaRecibidaCapitulo | None:
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
    factura_id = capitulo.factura_id
    await session.delete(capitulo)
    await session.flush()
    await _recalcular_totales_factura(session, factura_id)
    return True


# --- Mediciones y recálculo de partida ---


def _nueva_medicion(
    org_id: uuid.UUID, partida_id: uuid.UUID, datos: FacturaRecibidaMedicionCreate
) -> FacturaRecibidaMedicion:
    return FacturaRecibidaMedicion(
        organization_id=org_id,
        partida_id=partida_id,
        parcial=calc.parcial_de(datos.uds, datos.longitud, datos.anchura, datos.altura),
        **datos.model_dump(),
    )


async def _tiene_desglose(session: AsyncSession, partida_id: uuid.UUID) -> bool:
    total = await session.scalar(
        select(func.count())
        .select_from(FacturaRecibidaMedicion)
        .where(FacturaRecibidaMedicion.partida_id == partida_id)
    )
    return bool(total)


async def _recalcular_partida(session: AsyncSession, partida: FacturaRecibidaPartida) -> None:
    """Igual que `presupuesto_calculo.recalcular_partida`: si la partida tiene
    mediciones, `medicion` es su suma; sin ninguna, se respeta lo tecleado a
    mano. `importe` siempre es `medicion * precio` — no hay venta que
    recalcular en una factura recibida."""
    filas = await session.execute(
        select(FacturaRecibidaMedicion.parcial).where(
            FacturaRecibidaMedicion.partida_id == partida.id
        )
    )
    parciales = [fila[0] for fila in filas.all()]
    if parciales:
        partida.medicion = redondear_medicion(sum(parciales, Decimal("0.000")))
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    await session.flush()
    await _recalcular_totales_factura(session, partida.factura_id)


# --- Partidas ---


async def crear_partida(
    session: AsyncSession, capitulo_id: uuid.UUID, datos: FacturaRecibidaPartidaCreate
) -> FacturaRecibidaPartida | None:
    org_id = require_organization_id()
    capitulo = await session.scalar(
        select(FacturaRecibidaCapitulo).where(
            FacturaRecibidaCapitulo.id == capitulo_id,
            FacturaRecibidaCapitulo.organization_id == org_id,
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
        codigo = codigo or concepto.codigo
        resumen = resumen or concepto.resumen
        unidad = unidad or concepto.unidad
        precio = precio if precio is not None else concepto.precio
        texto = texto if texto is not None else concepto.texto
    elif not resumen:
        raise PartidaSinDatos(
            "Una partida alzada necesita al menos descripción; sin concepto no hay de dónde copiarla"
        )

    partida = FacturaRecibidaPartida(
        organization_id=org_id,
        factura_id=capitulo.factura_id,
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

    for medicion in datos.mediciones:
        session.add(_nueva_medicion(org_id, partida.id, medicion))
    await session.flush()
    await _recalcular_partida(session, partida)
    return partida


async def obtener_partida(
    session: AsyncSession, partida_id: uuid.UUID
) -> FacturaRecibidaPartida | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(FacturaRecibidaPartida)
        .options(selectinload(FacturaRecibidaPartida.mediciones))
        .where(FacturaRecibidaPartida.id == partida_id, FacturaRecibidaPartida.organization_id == org_id)
    )


async def actualizar_partida(
    session: AsyncSession, partida_id: uuid.UUID, datos: FacturaRecibidaPartidaUpdate
) -> FacturaRecibidaPartida | None:
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)

    medicion_manual = cambios.pop("medicion", None)
    sin_desglose = not await _tiene_desglose(session, partida.id)

    for campo, valor in cambios.items():
        setattr(partida, campo, valor)
    if "precio" in cambios:
        partida.precio = redondear_precio(partida.precio)

    if medicion_manual is not None and sin_desglose:
        partida.medicion = redondear_medicion(medicion_manual)
        partida.importe = redondear_precio(partida.medicion * partida.precio)
        await session.flush()
        await _recalcular_totales_factura(session, partida.factura_id)
        return partida

    await session.flush()
    await _recalcular_partida(session, partida)
    return partida


async def eliminar_partida(session: AsyncSession, partida_id: uuid.UUID) -> bool:
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    factura_id = partida.factura_id
    await session.delete(partida)
    await session.flush()
    await _recalcular_totales_factura(session, factura_id)
    return True


async def crear_medicion(
    session: AsyncSession, partida_id: uuid.UUID, datos: FacturaRecibidaMedicionCreate
) -> FacturaRecibidaMedicion | None:
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    medicion = _nueva_medicion(org_id, partida_id, datos)
    session.add(medicion)
    await session.flush()
    await _recalcular_partida(session, partida)
    return medicion


async def obtener_medicion(
    session: AsyncSession, medicion_id: uuid.UUID
) -> FacturaRecibidaMedicion | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(FacturaRecibidaMedicion).where(
            FacturaRecibidaMedicion.id == medicion_id,
            FacturaRecibidaMedicion.organization_id == org_id,
        )
    )


async def actualizar_medicion(
    session: AsyncSession, medicion_id: uuid.UUID, datos: FacturaRecibidaMedicionUpdate
) -> FacturaRecibidaMedicion | None:
    medicion = await obtener_medicion(session, medicion_id)
    if medicion is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(medicion, campo, valor)
    medicion.parcial = calc.parcial_de(medicion.uds, medicion.longitud, medicion.anchura, medicion.altura)
    await session.flush()

    partida = await obtener_partida(session, medicion.partida_id)
    if partida is not None:
        await _recalcular_partida(session, partida)
    return medicion


async def eliminar_medicion(session: AsyncSession, medicion_id: uuid.UUID) -> bool:
    medicion = await obtener_medicion(session, medicion_id)
    if medicion is None:
        return False
    partida_id = medicion.partida_id
    await session.delete(medicion)
    await session.flush()

    partida = await obtener_partida(session, partida_id)
    if partida is not None:
        if not await _tiene_desglose(session, partida_id):
            partida.medicion = Decimal("0.000")
        await _recalcular_partida(session, partida)
    return True


# --- Portapapeles: copiar/mover capítulos, partidas y mediciones (Fase 5) ---
#
# Calcado de `presupuestos.presupuesto_service`, muy simplificado: sin
# descomposición (no existe la tabla, no aplica nunca — factura recibida
# siempre de proveedor) y sin venta (no hay `_refrescar_venta` que llamar,
# `_recalcular_partida` ya se basta con `precio`/`importe`).
#
# `FacturaRecibida.base_imponible`/`cuota_iva`/`total` SÍ son columnas
# persistidas (a diferencia de `Pedido`, que suma en caliente), así que a
# diferencia de `presupuesto_service` hace falta recalcularlas explícitamente
# tras mover un capítulo o una partida a otra factura: `_recalcular_partida`
# ya lo hace por cada partida tocada, pero mover un capítulo entero
# reengancha sus partidas en bloque sin pasar por ahí, así que se recalcula
# la factura de origen y la de destino a mano.


async def pegar_partidas(
    session: AsyncSession, capitulo_id: uuid.UUID, partida_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve partidas enteras a otro capítulo (de la misma factura o
    de otra). Copiar clona la partida y sus mediciones, todo con ids nuevos;
    mover solo reengancha `capitulo_id`/`factura_id`."""
    org_id = require_organization_id()
    capitulo = await session.scalar(
        select(FacturaRecibidaCapitulo).where(
            FacturaRecibidaCapitulo.id == capitulo_id,
            FacturaRecibidaCapitulo.organization_id == org_id,
        )
    )
    if capitulo is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(FacturaRecibidaPartida).where(
                    FacturaRecibidaPartida.id.in_(partida_ids),
                    FacturaRecibidaPartida.organization_id == org_id,
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {p.id: p for p in origen}
    orden_pedido = [origen_por_id[pid] for pid in partida_ids if pid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(FacturaRecibidaPartida.orden)).where(
            FacturaRecibidaPartida.capitulo_id == capitulo_id
        )
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    facturas_origen: set[uuid.UUID] = set()
    afectadas: list[FacturaRecibidaPartida] = []
    for partida in orden_pedido:
        if alcance == "mover":
            facturas_origen.add(partida.factura_id)
            partida.capitulo_id = capitulo_id
            partida.factura_id = capitulo.factura_id
            partida.orden = orden
            afectadas.append(partida)
        else:
            nueva = await _clonar_partida(
                session, partida, org_id, capitulo.factura_id, capitulo_id, orden
            )
            afectadas.append(nueva)
        orden += 1

    await session.flush()
    await _recalcular_totales_factura(session, capitulo.factura_id)
    for factura_id_origen in facturas_origen - {capitulo.factura_id}:
        await _recalcular_totales_factura(session, factura_id_origen)
    return len(afectadas)


async def _clonar_partida(
    session: AsyncSession,
    partida: FacturaRecibidaPartida,
    org_id: uuid.UUID,
    factura_id: uuid.UUID,
    capitulo_id: uuid.UUID,
    orden: int,
) -> FacturaRecibidaPartida:
    """Clona una partida entera —mediciones incluidas— con ids nuevos. Sin
    descomposición: no existe para esta entidad. Compartido por
    `pegar_partidas` y `_clonar_capitulo`."""
    nueva = FacturaRecibidaPartida(
        organization_id=org_id,
        factura_id=factura_id,
        capitulo_id=capitulo_id,
        concepto_id=partida.concepto_id,
        codigo=partida.codigo,
        resumen=partida.resumen,
        texto=partida.texto,
        unidad=partida.unidad,
        precio=partida.precio,
        medicion=partida.medicion,
        importe=partida.importe,
        orden=orden,
    )
    session.add(nueva)
    await session.flush()

    mediciones = (
        await session.execute(
            select(FacturaRecibidaMedicion)
            .where(FacturaRecibidaMedicion.partida_id == partida.id)
            .order_by(FacturaRecibidaMedicion.orden)
        )
    ).scalars()
    for medicion in mediciones:
        session.add(
            FacturaRecibidaMedicion(
                organization_id=org_id,
                partida_id=nueva.id,
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
    capitulo: FacturaRecibidaCapitulo,
    org_id: uuid.UUID,
    factura_id: uuid.UUID,
    orden: int,
) -> FacturaRecibidaCapitulo:
    """Clona un capítulo entero —sus partidas y mediciones— con ids nuevos.
    Sin recursión: `FacturaRecibidaCapitulo` es de un solo nivel."""
    nuevo = FacturaRecibidaCapitulo(
        organization_id=org_id,
        factura_id=factura_id,
        codigo=capitulo.codigo,
        resumen=capitulo.resumen,
        texto=capitulo.texto,
        orden=orden,
    )
    session.add(nuevo)
    await session.flush()

    partidas = (
        await session.execute(
            select(FacturaRecibidaPartida)
            .where(FacturaRecibidaPartida.capitulo_id == capitulo.id)
            .order_by(FacturaRecibidaPartida.orden)
        )
    ).scalars()
    for i, partida in enumerate(partidas):
        await _clonar_partida(session, partida, org_id, factura_id, nuevo.id, i)

    return nuevo


async def pegar_capitulos(
    session: AsyncSession, factura_id: uuid.UUID, capitulo_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve capítulos enteros —con sus partidas y mediciones— a
    esta factura (de la misma o de otra). Sin `parent_id`:
    `FacturaRecibidaCapitulo` no anida."""
    org_id = require_organization_id()
    factura = await session.get(FacturaRecibida, factura_id)
    if factura is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(FacturaRecibidaCapitulo).where(
                    FacturaRecibidaCapitulo.id.in_(capitulo_ids),
                    FacturaRecibidaCapitulo.organization_id == org_id,
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {c.id: c for c in origen}
    orden_pedido = [origen_por_id[cid] for cid in capitulo_ids if cid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(FacturaRecibidaCapitulo.orden)).where(
            FacturaRecibidaCapitulo.factura_id == factura_id
        )
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    facturas_origen: set[uuid.UUID] = set()
    afectados = 0
    for capitulo in orden_pedido:
        if alcance == "mover":
            facturas_origen.add(capitulo.factura_id)
            capitulo.factura_id = factura_id
            capitulo.orden = orden
            partidas = (
                await session.execute(
                    select(FacturaRecibidaPartida).where(
                        FacturaRecibidaPartida.capitulo_id == capitulo.id
                    )
                )
            ).scalars()
            for partida in partidas:
                partida.factura_id = factura_id
        else:
            await _clonar_capitulo(session, capitulo, org_id, factura_id, orden)
        afectados += 1
        orden += 1

    await session.flush()
    await _recalcular_totales_factura(session, factura_id)
    for factura_id_origen in facturas_origen - {factura_id}:
        await _recalcular_totales_factura(session, factura_id_origen)
    return afectados


async def pegar_mediciones(
    session: AsyncSession, partida_id: uuid.UUID, medicion_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve mediciones sueltas a otra partida."""
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(FacturaRecibidaMedicion).where(
                    FacturaRecibidaMedicion.id.in_(medicion_ids),
                    FacturaRecibidaMedicion.organization_id == org_id,
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {m.id: m for m in origen}
    orden_pedido = [origen_por_id[mid] for mid in medicion_ids if mid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(FacturaRecibidaMedicion.orden)).where(
            FacturaRecibidaMedicion.partida_id == partida_id
        )
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    partidas_origen: set[uuid.UUID] = set()
    for medicion in orden_pedido:
        partidas_origen.add(medicion.partida_id)
        if alcance == "mover":
            medicion.partida_id = partida_id
            medicion.orden = orden
        else:
            session.add(
                FacturaRecibidaMedicion(
                    organization_id=org_id,
                    partida_id=partida_id,
                    comentario=medicion.comentario,
                    uds=medicion.uds,
                    longitud=medicion.longitud,
                    anchura=medicion.anchura,
                    altura=medicion.altura,
                    parcial=medicion.parcial,
                    orden=orden,
                )
            )
        orden += 1
    await session.flush()

    await _recalcular_partida(session, partida)
    if alcance == "mover":
        for origen_id in partidas_origen - {partida_id}:
            origen_partida = await obtener_partida(session, origen_id)
            if origen_partida is not None:
                # Si se llevó la última medición, la partida de origen se
                # queda sin desglose y `_recalcular_partida` ya no toca la
                # medición (para no pisar una manual) — aquí sí hay que
                # ponerla a cero explícitamente (mismo caso que
                # `eliminar_medicion`).
                if not await _tiene_desglose(session, origen_id):
                    origen_partida.medicion = Decimal("0.000")
                await _recalcular_partida(session, origen_partida)
    return len(orden_pedido)
