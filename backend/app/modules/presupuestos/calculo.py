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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redondeo import redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.presupuestos.models import Concepto, Descomposicion, OrigenPrecio

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


async def calcular_precio(session: AsyncSession, concepto: Concepto) -> Decimal:
    """Precio que le corresponde al concepto según su origen de precio.

    No lo persiste; devolverlo aparte permite saber si ha cambiado y cortar la
    propagación cuando no lo ha hecho.
    """
    if concepto.origen_precio == OrigenPrecio.MANUAL:
        return concepto.precio

    if concepto.origen_precio == OrigenPrecio.PRODUCTO:
        if concepto.producto_id is None:
            return concepto.precio
        # presupuestos depende de catalogo, así que la importación es legítima.
        from app.modules.catalogo.service import precio_referencia

        referencia = await precio_referencia(session, concepto.producto_id)
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
            # Se vuelca antes de seguir subiendo: el padre lee el precio del
            # hijo por SQL, no desde el objeto en memoria.
            await session.flush()

    # Último tramo de la cascada: del cuadro de precios a las partidas de los
    # presupuestos que aún siguen al cuadro (los no bloqueados).
    if modificados:
        from app.modules.presupuestos.presupuesto_calculo import propagar_a_partidas

        await propagar_a_partidas(session, modificados)

    return modificados


async def recalcular_por_producto(
    session: AsyncSession, producto_id: uuid.UUID
) -> list[uuid.UUID]:
    """Punto de entrada de la cascada cuando cambia una tarifa de proveedor.

    Lo invoca el manejador del evento que emite `catalogo`.
    """
    org_id = require_organization_id()
    afectados = (
        await session.execute(
            select(Concepto.id).where(
                Concepto.producto_id == producto_id,
                Concepto.origen_precio == OrigenPrecio.PRODUCTO,
                Concepto.organization_id == org_id,
            )
        )
    ).scalars()

    modificados: list[uuid.UUID] = []
    for concepto_id in afectados:
        modificados.extend(await recalcular_cascada(session, concepto_id))
    return modificados


async def donde_se_usa(
    session: AsyncSession, concepto_id: uuid.UUID
) -> list[tuple[Concepto, Decimal]]:
    """Conceptos que contienen a este directamente, con su rendimiento.

    Se consulta antes de borrar y para navegar hacia arriba en el editor.
    """
    org_id = require_organization_id()
    filas = await session.execute(
        select(Concepto, Descomposicion.rendimiento)
        .join(Descomposicion, Descomposicion.padre_id == Concepto.id)
        .where(
            Descomposicion.hijo_id == concepto_id,
            Concepto.organization_id == org_id,
        )
        .order_by(Concepto.codigo)
    )
    return [(fila[0], fila[1]) for fila in filas.all()]
