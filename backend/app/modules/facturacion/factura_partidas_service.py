"""Capítulos, partidas, mediciones y descompuesto de la Factura de venta
(Fase 2).

Calcado de `presupuestos.presupuesto_service`, con dos diferencias:
`FacturaCapitulo` es de un solo nivel (sin subcapítulos, a diferencia de
`presupuestos.Capitulo`) y, al ser una factura de venta siempre de cliente,
el descompuesto está siempre disponible en sus partidas — a diferencia de
`compras.pedido_service`, aquí no hace falta ningún
`DescomposicionNoDisponible`.

Además, tras cualquier alta/baja/edición de partida, medición o
descomposición se recalcula `Factura.base_imponible` (suma de
`importe_venta` de sus partidas) y, con ella, `cuota_iva`/`total` — pero
SOLO si la factura ya tiene alguna `FacturaPartida`. Una factura sin
desglose (como la `FAC00001` real, tecleada a mano antes de existir esta
jerarquía) conserva lo que se haya escrito directamente: no se le impone un
0,00 por no tener partidas.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.facturacion.factura_partidas_schemas import (
    FacturaCapituloCreate,
    FacturaCapituloUpdate,
    FacturaMedicionCreate,
    FacturaMedicionUpdate,
    FacturaPartidaCreate,
    FacturaPartidaUpdate,
)
from app.modules.facturacion.models import (
    Factura,
    FacturaCapitulo,
    FacturaMedicion,
    FacturaPartida,
    FacturaPartidaDescomposicion,
)
from app.modules.facturacion.service import _calcular_iva
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos.models import Concepto, Descomposicion


class ConceptoInvalido(Exception):
    pass


class PartidaSinDatos(Exception):
    pass


# --- Total de la factura ---


async def _recalcular_totales_factura(session: AsyncSession, factura_id: uuid.UUID) -> None:
    factura = await session.get(Factura, factura_id)
    if factura is None:
        return
    tiene_partidas = await session.scalar(
        select(func.count()).select_from(FacturaPartida).where(FacturaPartida.factura_id == factura_id)
    )
    if not tiene_partidas:
        return
    suma = await session.scalar(
        select(func.coalesce(func.sum(FacturaPartida.importe_venta), 0)).where(
            FacturaPartida.factura_id == factura_id
        )
    )
    factura.base_imponible = redondear_precio(Decimal(suma))
    factura.cuota_iva = _calcular_iva(
        factura.base_imponible, factura.tipo_iva, factura.inversion_sujeto_pasivo
    )
    factura.total = redondear_precio(factura.base_imponible + factura.cuota_iva)
    await session.flush()


# --- Capítulos ---


async def _siguiente_codigo_capitulo(session: AsyncSession, factura_id: uuid.UUID) -> str:
    """Numeración plana: 01, 02... — sin subcapítulos."""
    hermanos = (
        await session.execute(
            select(FacturaCapitulo.codigo).where(FacturaCapitulo.factura_id == factura_id)
        )
    ).scalars()
    maximo = 0
    for codigo in hermanos:
        ultimo = codigo.rsplit(".", 1)[-1]
        if ultimo.isdigit():
            maximo = max(maximo, int(ultimo))
    return f"{maximo + 1:02d}"


async def obtener_capitulo(session: AsyncSession, capitulo_id: uuid.UUID) -> FacturaCapitulo | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(FacturaCapitulo).where(
            FacturaCapitulo.id == capitulo_id, FacturaCapitulo.organization_id == org_id
        )
    )


async def cargar_capitulos(session: AsyncSession, factura_id: uuid.UUID) -> list[FacturaCapitulo]:
    """El árbol completo de la factura, ya anidado, con mediciones y
    descomposición cargadas de un tirón. `tiene_desglose`/`descomposicion_
    propia` no son columnas: se calculan aquí a partir de las relaciones ya
    cargadas y se dejan como atributo de instancia (mismo criterio que
    `pedido_service.cargar_capitulos`/`presupuesto_service.arbol_y_totales`)."""
    org_id = require_organization_id()
    capitulos = (
        await session.execute(
            select(FacturaCapitulo)
            .where(FacturaCapitulo.factura_id == factura_id, FacturaCapitulo.organization_id == org_id)
            .options(
                selectinload(FacturaCapitulo.partidas).selectinload(FacturaPartida.mediciones),
                selectinload(FacturaCapitulo.partidas).selectinload(FacturaPartida.descomposicion),
            )
            .order_by(FacturaCapitulo.orden, FacturaCapitulo.codigo)
        )
    ).scalars()
    resultado = list(capitulos)
    for capitulo in resultado:
        for partida in capitulo.partidas:
            partida.tiene_desglose = len(partida.mediciones) > 0
            partida.descomposicion_propia = len(partida.descomposicion) > 0
    return resultado


async def crear_capitulo(
    session: AsyncSession, factura_id: uuid.UUID, datos: FacturaCapituloCreate
) -> FacturaCapitulo | None:
    org_id = require_organization_id()
    factura = await session.scalar(
        select(Factura).where(Factura.id == factura_id, Factura.organization_id == org_id)
    )
    if factura is None:
        return None
    codigo = datos.codigo or await _siguiente_codigo_capitulo(session, factura_id)
    capitulo = FacturaCapitulo(
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
    session: AsyncSession, capitulo_id: uuid.UUID, datos: FacturaCapituloUpdate
) -> FacturaCapitulo | None:
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
    org_id: uuid.UUID, partida_id: uuid.UUID, datos: FacturaMedicionCreate
) -> FacturaMedicion:
    return FacturaMedicion(
        organization_id=org_id,
        partida_id=partida_id,
        parcial=calc.parcial_de(datos.uds, datos.longitud, datos.anchura, datos.altura),
        **datos.model_dump(),
    )


async def _tiene_desglose(session: AsyncSession, partida_id: uuid.UUID) -> bool:
    total = await session.scalar(
        select(func.count()).select_from(FacturaMedicion).where(FacturaMedicion.partida_id == partida_id)
    )
    return bool(total)


async def _recalcular_partida(session: AsyncSession, partida: FacturaPartida) -> None:
    """Igual que `presupuesto_calculo.recalcular_partida`: si la partida tiene
    mediciones, `medicion` es su suma; sin ninguna, se respeta lo tecleado a
    mano. `importe` siempre es `medicion * precio`."""
    filas = await session.execute(
        select(FacturaMedicion.parcial).where(FacturaMedicion.partida_id == partida.id)
    )
    parciales = [fila[0] for fila in filas.all()]
    if parciales:
        partida.medicion = redondear_medicion(sum(parciales, Decimal("0.000")))
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    await session.flush()


async def _refrescar_venta(session: AsyncSession, factura: Factura, partida: FacturaPartida) -> None:
    """Recalcula precio_venta/importe_venta tras tocar coste o medición.

    Una factura de venta es siempre de cliente, así que a diferencia de
    `compras.pedido_service` esto se aplica siempre, sin condición de tipo.
    `venta_unitaria()` con método CLASICO (el por defecto — `Factura` no
    tiene `gastos_generales`/`beneficio_industrial` como sí tiene
    `Presupuesto`) devuelve el coste sin recargo, así que "clásico" en una
    Factura equivale deliberadamente a "sin margen" (misma simplificación que
    en `Pedido`, ver su `_refrescar_venta`).
    """
    if not partida.venta_bloqueada:
        partida.precio_venta = calc.venta_unitaria(
            partida.precio, factura.metodo_calculo, factura.porcentaje_metodo
        )
    partida.importe_venta = redondear_precio(partida.medicion * partida.precio_venta)
    await session.flush()
    await _recalcular_totales_factura(session, factura.id)


# --- Partidas ---


async def crear_partida(
    session: AsyncSession, capitulo_id: uuid.UUID, datos: FacturaPartidaCreate
) -> FacturaPartida | None:
    org_id = require_organization_id()
    capitulo = await session.scalar(
        select(FacturaCapitulo).where(
            FacturaCapitulo.id == capitulo_id, FacturaCapitulo.organization_id == org_id
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

    partida = FacturaPartida(
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
    factura = await session.get(Factura, capitulo.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    return partida


async def obtener_partida(session: AsyncSession, partida_id: uuid.UUID) -> FacturaPartida | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(FacturaPartida)
        .options(
            selectinload(FacturaPartida.mediciones), selectinload(FacturaPartida.descomposicion)
        )
        .where(FacturaPartida.id == partida_id, FacturaPartida.organization_id == org_id)
    )


async def actualizar_partida(
    session: AsyncSession, partida_id: uuid.UUID, datos: FacturaPartidaUpdate
) -> FacturaPartida | None:
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

    factura = await session.get(Factura, partida.factura_id)

    if medicion_manual is not None and sin_desglose:
        partida.medicion = redondear_medicion(medicion_manual)
        partida.importe = redondear_precio(partida.medicion * partida.precio)
        if factura is not None:
            await _refrescar_venta(session, factura, partida)
        else:
            await session.flush()
        return partida

    await session.flush()
    await _recalcular_partida(session, partida)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
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
    session: AsyncSession, partida_id: uuid.UUID, datos: FacturaMedicionCreate
) -> FacturaMedicion | None:
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None
    medicion = _nueva_medicion(org_id, partida_id, datos)
    session.add(medicion)
    await session.flush()
    await _recalcular_partida(session, partida)
    factura = await session.get(Factura, partida.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    return medicion


async def obtener_medicion(session: AsyncSession, medicion_id: uuid.UUID) -> FacturaMedicion | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(FacturaMedicion).where(
            FacturaMedicion.id == medicion_id, FacturaMedicion.organization_id == org_id
        )
    )


async def actualizar_medicion(
    session: AsyncSession, medicion_id: uuid.UUID, datos: FacturaMedicionUpdate
) -> FacturaMedicion | None:
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
        factura = await session.get(Factura, partida.factura_id)
        if factura is not None:
            await _refrescar_venta(session, factura, partida)
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
        factura = await session.get(Factura, partida.factura_id)
        if factura is not None:
            await _refrescar_venta(session, factura, partida)
    return True


# --- Descompuesto de la partida (siempre disponible: la factura es siempre
#     de cliente) ---


async def _lineas_heredadas(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[tuple[Descomposicion, Concepto]]:
    filas = await session.execute(
        select(Descomposicion, Concepto)
        .join(Concepto, Concepto.id == Descomposicion.hijo_id)
        .where(Descomposicion.padre_id == concepto_id)
        .order_by(Descomposicion.orden)
    )
    return [(linea, hijo) for linea, hijo in filas.all()]


async def independizar_descomposicion(
    session: AsyncSession, partida: FacturaPartida
) -> list[FacturaPartidaDescomposicion]:
    org_id = require_organization_id()
    existentes = (
        await session.execute(
            select(FacturaPartidaDescomposicion)
            .where(FacturaPartidaDescomposicion.partida_id == partida.id)
            .order_by(FacturaPartidaDescomposicion.orden)
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

    nuevas: list[FacturaPartidaDescomposicion] = []
    for orden, (linea, hijo) in enumerate(await _lineas_heredadas(session, concepto.id)):
        fila = FacturaPartidaDescomposicion(
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
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return None

    propias = (
        await session.execute(
            select(FacturaPartidaDescomposicion)
            .where(FacturaPartidaDescomposicion.partida_id == partida.id)
            .order_by(FacturaPartidaDescomposicion.orden)
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


async def _precio_desde_descomposicion_propia(
    session: AsyncSession, partida: FacturaPartida
) -> Decimal | None:
    filas = await session.execute(
        select(
            FacturaPartidaDescomposicion.rendimiento,
            FacturaPartidaDescomposicion.factor,
            FacturaPartidaDescomposicion.precio,
        ).where(FacturaPartidaDescomposicion.partida_id == partida.id)
    )
    lineas = filas.all()
    if not lineas:
        return None

    coste_directo = Decimal("0.00")
    for rendimiento, factor, precio in lineas:
        coste_directo += redondear_precio(rendimiento * factor * precio)

    if partida.costes_indirectos:
        porcentaje = Decimal("1") + partida.costes_indirectos / Decimal("100")
        return redondear_precio(coste_directo * porcentaje)
    return redondear_precio(coste_directo)


async def _recalcular_desde_descomposicion(session: AsyncSession, partida: FacturaPartida) -> None:
    nuevo = await _precio_desde_descomposicion_propia(session, partida)
    if nuevo is None:
        return
    partida.precio = nuevo
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    await session.flush()


async def anadir_componente(
    session: AsyncSession,
    partida_id: uuid.UUID,
    hijo_id: uuid.UUID,
    rendimiento: Decimal,
    factor: Decimal,
) -> bool:
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
        .select_from(FacturaPartidaDescomposicion)
        .where(FacturaPartidaDescomposicion.partida_id == partida.id)
    )
    session.add(
        FacturaPartidaDescomposicion(
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
    await _recalcular_desde_descomposicion(session, partida)
    factura = await session.get(Factura, partida.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    return True


async def quitar_componente(
    session: AsyncSession, partida_id: uuid.UUID, linea_id: uuid.UUID
) -> bool:
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return False
    linea = await session.scalar(
        select(FacturaPartidaDescomposicion).where(
            FacturaPartidaDescomposicion.id == linea_id,
            FacturaPartidaDescomposicion.partida_id == partida_id,
            FacturaPartidaDescomposicion.organization_id == org_id,
        )
    )
    if linea is None:
        return False
    await session.delete(linea)
    await session.flush()
    await _recalcular_desde_descomposicion(session, partida)
    factura = await session.get(Factura, partida.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    return True


async def cambiar_precio_componente(
    session: AsyncSession,
    partida_id: uuid.UUID,
    hijo_id: uuid.UUID,
    precio: Decimal,
    alcance: str,
) -> int:
    """Con alcance `partida` afecta solo a esa; con `factura`, a todas las
    partidas de la misma factura que lleven ese componente."""
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return 0

    objetivo = [partida]
    if alcance == "factura":
        org_id = require_organization_id()
        hermanas = (
            await session.execute(
                select(FacturaPartida)
                .options(selectinload(FacturaPartida.mediciones))
                .where(
                    FacturaPartida.factura_id == partida.factura_id,
                    FacturaPartida.organization_id == org_id,
                    FacturaPartida.id != partida.id,
                )
            )
        ).scalars()
        objetivo.extend(hermanas)

    factura = await session.get(Factura, partida.factura_id)
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
        await _recalcular_desde_descomposicion(session, candidata)
        if factura is not None:
            await _refrescar_venta(session, factura, candidata)
        afectadas += 1

    return afectadas


async def cambiar_rendimiento_componente(
    session: AsyncSession, partida_id: uuid.UUID, hijo_id: uuid.UUID, rendimiento: Decimal
) -> bool:
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
    await _recalcular_desde_descomposicion(session, partida)
    factura = await session.get(Factura, partida.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    return True


async def cambiar_resumen_componente(
    session: AsyncSession, partida_id: uuid.UUID, hijo_id: uuid.UUID, resumen: str
) -> bool:
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


# --- Portapapeles: copiar/mover capítulos, partidas, mediciones y
# componentes de descompuesto (Fase 5) ---
#
# Calcado de `presupuestos.presupuesto_service`, con dos diferencias:
# `FacturaCapitulo` es de un solo nivel (sin recursión ni comprobación de
# ciclos) y el descompuesto está siempre disponible (factura de venta =
# siempre cliente), así que a diferencia de `compras.pedido_service` no hace
# falta ningún `DescomposicionNoDisponible`.
#
# A diferencia de `Pedido` (cuyo total se suma en caliente), `Factura.
# base_imponible`/`cuota_iva`/`total` SÍ son columnas persistidas — así que,
# a diferencia de `presupuesto_service`, aquí hace falta recalcularlas
# explícitamente tras mover un capítulo o una partida a otra factura: mover
# una partida sola ya lo hace `_refrescar_venta` (llamada tras cada cambio),
# pero mover un capítulo entero reengancha sus partidas en bloque sin pasar
# por ahí, así que se recalcula la factura de origen y la de destino a mano.


async def pegar_partidas(
    session: AsyncSession, capitulo_id: uuid.UUID, partida_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve partidas enteras a otro capítulo (de la misma factura o
    de otra). Copiar clona la partida, su descompuesto propio y sus
    mediciones, todo con ids nuevos; mover solo reengancha
    `capitulo_id`/`factura_id`."""
    org_id = require_organization_id()
    capitulo = await session.scalar(
        select(FacturaCapitulo).where(
            FacturaCapitulo.id == capitulo_id, FacturaCapitulo.organization_id == org_id
        )
    )
    if capitulo is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(FacturaPartida).where(
                    FacturaPartida.id.in_(partida_ids), FacturaPartida.organization_id == org_id
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {p.id: p for p in origen}
    orden_pedido = [origen_por_id[pid] for pid in partida_ids if pid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(FacturaPartida.orden)).where(FacturaPartida.capitulo_id == capitulo_id)
    )
    orden = int(siguiente + 1) if siguiente is not None else 0

    factura = await session.get(Factura, capitulo.factura_id)
    facturas_origen: set[uuid.UUID] = set()
    afectadas: list[FacturaPartida] = []
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
    if factura is not None:
        for p in afectadas:
            await _refrescar_venta(session, factura, p)
    for factura_id_origen in facturas_origen - {capitulo.factura_id}:
        await _recalcular_totales_factura(session, factura_id_origen)
    return len(afectadas)


async def _clonar_partida(
    session: AsyncSession,
    partida: FacturaPartida,
    org_id: uuid.UUID,
    factura_id: uuid.UUID,
    capitulo_id: uuid.UUID,
    orden: int,
) -> FacturaPartida:
    """Clona una partida entera —descompuesto propio y mediciones
    incluidos— con ids nuevos. Compartido por `pegar_partidas` y
    `_clonar_capitulo`."""
    nueva = FacturaPartida(
        organization_id=org_id,
        factura_id=factura_id,
        capitulo_id=capitulo_id,
        concepto_id=partida.concepto_id,
        codigo=partida.codigo,
        resumen=partida.resumen,
        texto=partida.texto,
        unidad=partida.unidad,
        precio=partida.precio,
        costes_indirectos=partida.costes_indirectos,
        precio_venta=partida.precio_venta,
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
            select(FacturaPartidaDescomposicion)
            .where(FacturaPartidaDescomposicion.partida_id == partida.id)
            .order_by(FacturaPartidaDescomposicion.orden)
        )
    ).scalars()
    for linea in propias:
        session.add(
            FacturaPartidaDescomposicion(
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
            select(FacturaMedicion)
            .where(FacturaMedicion.partida_id == partida.id)
            .order_by(FacturaMedicion.orden)
        )
    ).scalars()
    for medicion in mediciones:
        session.add(
            FacturaMedicion(
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
    capitulo: FacturaCapitulo,
    org_id: uuid.UUID,
    factura_id: uuid.UUID,
    orden: int,
) -> FacturaCapitulo:
    """Clona un capítulo entero —sus partidas, con descompuesto y
    mediciones— con ids nuevos. Sin recursión: `FacturaCapitulo` es de un
    solo nivel."""
    nuevo = FacturaCapitulo(
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
            select(FacturaPartida)
            .where(FacturaPartida.capitulo_id == capitulo.id)
            .order_by(FacturaPartida.orden)
        )
    ).scalars()
    for i, partida in enumerate(partidas):
        await _clonar_partida(session, partida, org_id, factura_id, nuevo.id, i)

    return nuevo


async def pegar_capitulos(
    session: AsyncSession, factura_id: uuid.UUID, capitulo_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve capítulos enteros —con sus partidas, descompuesto y
    mediciones— a esta factura (de la misma o de otra). Sin `parent_id`:
    `FacturaCapitulo` no anida."""
    org_id = require_organization_id()
    factura = await session.get(Factura, factura_id)
    if factura is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(FacturaCapitulo).where(
                    FacturaCapitulo.id.in_(capitulo_ids), FacturaCapitulo.organization_id == org_id
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {c.id: c for c in origen}
    orden_pedido = [origen_por_id[cid] for cid in capitulo_ids if cid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(FacturaCapitulo.orden)).where(FacturaCapitulo.factura_id == factura_id)
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
                    select(FacturaPartida).where(FacturaPartida.capitulo_id == capitulo.id)
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
                select(FacturaMedicion).where(
                    FacturaMedicion.id.in_(medicion_ids), FacturaMedicion.organization_id == org_id
                )
            )
        ).scalars()
    )
    if not origen:
        return 0
    origen_por_id = {m.id: m for m in origen}
    orden_pedido = [origen_por_id[mid] for mid in medicion_ids if mid in origen_por_id]

    siguiente = await session.scalar(
        select(func.max(FacturaMedicion.orden)).where(FacturaMedicion.partida_id == partida_id)
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
                FacturaMedicion(
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
    factura = await session.get(Factura, partida.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    if alcance == "mover":
        for origen_id in partidas_origen - {partida_id}:
            origen_partida = await obtener_partida(session, origen_id)
            if origen_partida is not None:
                if not await _tiene_desglose(session, origen_id):
                    origen_partida.medicion = Decimal("0.000")
                await _recalcular_partida(session, origen_partida)
                factura_origen = await session.get(Factura, origen_partida.factura_id)
                if factura_origen is not None:
                    await _refrescar_venta(session, factura_origen, origen_partida)
    return len(orden_pedido)


async def pegar_componentes_descompuesto(
    session: AsyncSession, partida_id: uuid.UUID, linea_ids: list[uuid.UUID], alcance: str
) -> int:
    """Copia o mueve componentes de un descompuesto a otra partida,
    independizando el destino del banco si aún lo heredaba."""
    org_id = require_organization_id()
    partida = await obtener_partida(session, partida_id)
    if partida is None:
        return 0

    origen = list(
        (
            await session.execute(
                select(FacturaPartidaDescomposicion).where(
                    FacturaPartidaDescomposicion.id.in_(linea_ids),
                    FacturaPartidaDescomposicion.organization_id == org_id,
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
        select(func.max(FacturaPartidaDescomposicion.orden)).where(
            FacturaPartidaDescomposicion.partida_id == partida_id
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
                FacturaPartidaDescomposicion(
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

    await _recalcular_desde_descomposicion(session, partida)
    factura = await session.get(Factura, partida.factura_id)
    if factura is not None:
        await _refrescar_venta(session, factura, partida)
    if alcance == "mover":
        for origen_id in partidas_origen - {partida_id}:
            origen_partida = await obtener_partida(session, origen_id)
            if origen_partida is not None:
                await _recalcular_desde_descomposicion(session, origen_partida)
                factura_origen = await session.get(Factura, origen_partida.factura_id)
                if factura_origen is not None:
                    await _refrescar_venta(session, factura_origen, origen_partida)
    return len(orden_pedido)
