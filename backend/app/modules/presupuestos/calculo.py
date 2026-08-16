"""Motor de cálculo y recálculo en cascada.

El precio de un concepto está materializado en la tabla, no se calcula al leer:
un presupuesto de miles de partidas no puede recorrer el árbol entero en cada
consulta. A cambio, cualquier cambio que afecte a un precio tiene que
propagarse hacia arriba, y de eso se ocupa este módulo.

Convención de redondeo (Presto): se redondea el importe de **cada línea** del
descompuesto a dos decimales y después la suma. Es lo que hace que el
descompuesto impreso cuadre columna a columna; sumar con todos los decimales y
redondear al final produce descuadres de céntimos entre el papel y el total.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redondeo import redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.presupuestos.models import (
    Concepto,
    Descomposicion,
    HistoricoPrecioConcepto,
    OrigenPrecio,
    PrecioSuministro,
)

# Tope de profundidad del árbol. Existe como red de seguridad: los ciclos se
# impiden al insertar, pero un dato corrupto no debe colgar una request.
PROFUNDIDAD_MAXIMA = 25


class CicloDetectado(Exception):
    pass


async def crearia_ciclo(
    session: AsyncSession, padre_id: uuid.UUID, hijo_id: uuid.UUID
) -> bool:
    """¿Colgar `hijo` de `padre` cerraría un ciclo?

    Ocurre si el padre ya es alcanzable descendiendo desde el hijo, o si son el
    mismo concepto.
    """
    if padre_id == hijo_id:
        return True

    consulta = text(
        """
        WITH RECURSIVE descendientes(id, profundidad) AS (
            SELECT CAST(:hijo AS uuid), 0
          UNION ALL
            SELECT d.hijo_id, dd.profundidad + 1
            FROM presupuestos.descomposicion d
            JOIN descendientes dd ON d.padre_id = dd.id
            WHERE dd.profundidad < :max_prof
        )
        SELECT 1 FROM descendientes WHERE id = CAST(:padre AS uuid) LIMIT 1
        """
    )
    encontrado = await session.scalar(
        consulta,
        {"hijo": str(hijo_id), "padre": str(padre_id), "max_prof": PROFUNDIDAD_MAXIMA},
    )
    return encontrado is not None


async def ancestros_en_orden(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[uuid.UUID]:
    """El concepto y todos los que dependen de él, en orden de recálculo.

    Se ordena por la distancia **máxima** al concepto de partida. Con un grafo
    acíclico eso es un orden topológico válido: si A contiene a B, la distancia
    máxima de A es al menos la de B más uno, así que B siempre se recalcula
    antes que A. Importa cuando hay rombos — un auxiliar que entra en dos
    unitarios que a su vez entran en el mismo funcional.
    """
    consulta = text(
        """
        WITH RECURSIVE subida(id, profundidad) AS (
            SELECT CAST(:inicio AS uuid), 0
          UNION ALL
            SELECT d.padre_id, s.profundidad + 1
            FROM presupuestos.descomposicion d
            JOIN subida s ON d.hijo_id = s.id
            WHERE s.profundidad < :max_prof
        )
        SELECT id
        FROM subida
        GROUP BY id
        ORDER BY MAX(profundidad)
        """
    )
    filas = await session.execute(
        consulta, {"inicio": str(concepto_id), "max_prof": PROFUNDIDAD_MAXIMA}
    )
    return [fila[0] for fila in filas.all()]


async def precio_referencia(
    session: AsyncSession, concepto_id: uuid.UUID
) -> Decimal | None:
    """Precio de suministro que usará el precio básico.

    Preferencia: la tarifa marcada como preferente; en su defecto, la vigente
    más reciente. Se devuelve neto de descuento y sin redondear.

    Vivía en `catalogo.service` cuando `PrecioSuministro` colgaba de
    `Producto` (Fase 2); se muda aquí al fusionarse `Producto` en `Concepto`
    (Fase 25).
    """
    org_id = require_organization_id()
    rows = await session.execute(
        select(PrecioSuministro)
        .where(
            PrecioSuministro.concepto_id == concepto_id,
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


async def calcular_precio(session: AsyncSession, concepto: Concepto) -> Decimal:
    """Precio que le corresponde al concepto según su origen de precio.

    No lo persiste; devolverlo aparte permite saber si ha cambiado y cortar la
    propagación cuando no lo ha hecho.
    """
    if concepto.origen_precio == OrigenPrecio.MANUAL:
        return concepto.precio

    if concepto.origen_precio == OrigenPrecio.PRODUCTO:
        referencia = await precio_referencia(session, concepto.id)
        return redondear_precio(referencia) if referencia is not None else Decimal("0.00")

    return await _precio_desde_descomposicion(session, concepto)


async def _precio_desde_descomposicion(
    session: AsyncSession, concepto: Concepto
) -> Decimal:
    filas = await session.execute(
        select(Descomposicion.rendimiento, Descomposicion.factor, Concepto.precio)
        .join(Concepto, Concepto.id == Descomposicion.hijo_id)
        .where(Descomposicion.padre_id == concepto.id)
    )

    coste_directo = Decimal("0.00")
    for rendimiento, factor, precio_hijo in filas.all():
        # Redondeo por línea, no al final: así el descompuesto impreso suma.
        coste_directo += redondear_precio(rendimiento * factor * precio_hijo)

    if concepto.costes_indirectos:
        porcentaje = Decimal("1") + concepto.costes_indirectos / Decimal("100")
        return redondear_precio(coste_directo * porcentaje)
    return redondear_precio(coste_directo)


async def registrar_historico(session: AsyncSession, concepto: Concepto) -> None:
    """Añade una fila al histórico de precios del concepto.

    Append-only: nunca se actualiza ni se borra una fila existente, es lo que
    permite responder "qué costes ha tenido" en su ficha. Se llama tanto al
    fijar el precio inicial (alta) como cada vez que la cascada lo cambia de
    verdad.
    """
    session.add(
        HistoricoPrecioConcepto(
            organization_id=concepto.organization_id,
            concepto_id=concepto.id,
            precio=concepto.precio,
            origen_precio=concepto.origen_precio,
        )
    )


async def recalcular_cascada(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[uuid.UUID]:
    """Recalcula el concepto y propaga a todo lo que depende de él.

    Devuelve los conceptos cuyo precio ha cambiado realmente.
    """
    org_id = require_organization_id()
    orden = await ancestros_en_orden(session, concepto_id)
    if not orden:
        return []

    conceptos = {
        c.id: c
        for c in (
            await session.execute(
                select(Concepto).where(
                    Concepto.id.in_(orden), Concepto.organization_id == org_id
                )
            )
        ).scalars()
    }

    modificados: list[uuid.UUID] = []
    for cid in orden:
        concepto = conceptos.get(cid)
        if concepto is None:
            continue
        nuevo = await calcular_precio(session, concepto)
        if nuevo != concepto.precio:
            concepto.precio = nuevo
            modificados.append(cid)
            await registrar_historico(session, concepto)
            # Se vuelca antes de seguir subiendo: el padre lee el precio del
            # hijo por SQL, no desde el objeto en memoria.
            await session.flush()

    # Último tramo de la cascada: del cuadro de precios a las partidas de los
    # presupuestos que aún siguen al cuadro (los no bloqueados).
    if modificados:
        from app.modules.presupuestos.presupuesto_calculo import propagar_a_partidas

        await propagar_a_partidas(session, modificados)

    return modificados


async def donde_se_usa(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[tuple[Concepto, Decimal]]:
    """Conceptos que contienen a este, directa o indirectamente.

    El rendimiento devuelto es el efectivo: cuánto de este concepto entra por
    cada unidad del ancestro, acumulando `rendimiento x factor` a lo largo de
    la cadena y sumando entre rutas distintas cuando hay rombos (un auxiliar
    que entra dos veces en el mismo unitario por caminos diferentes consume el
    doble, no el mismo rendimiento contado una vez).
    """
    org_id = require_organization_id()
    consulta = text(
        """
        WITH RECURSIVE subida(id, profundidad, acumulado) AS (
            SELECT d.padre_id, 1, d.rendimiento * d.factor
            FROM presupuestos.descomposicion d
            WHERE d.hijo_id = CAST(:inicio AS uuid)
          UNION ALL
            SELECT d.padre_id, s.profundidad + 1, s.acumulado * d.rendimiento * d.factor
            FROM presupuestos.descomposicion d
            JOIN subida s ON d.hijo_id = s.id
            WHERE s.profundidad < :max_prof
        )
        SELECT id, SUM(acumulado)
        FROM subida
        GROUP BY id
        """
    )
    filas = await session.execute(
        consulta, {"inicio": str(concepto_id), "max_prof": PROFUNDIDAD_MAXIMA}
    )
    acumulado: dict[uuid.UUID, Decimal] = {fila[0]: fila[1] for fila in filas.all()}
    if not acumulado:
        return []

    conceptos = (
        await session.execute(
            select(Concepto).where(
                Concepto.id.in_(acumulado), Concepto.organization_id == org_id
            )
        )
    ).scalars()
    return sorted(
        ((concepto, acumulado[concepto.id]) for concepto in conceptos),
        key=lambda par: par[0].codigo,
    )
