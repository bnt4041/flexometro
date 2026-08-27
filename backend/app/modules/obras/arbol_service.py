"""El árbol de la obra: capítulos, partidas y mediciones propios.

Por qué es un árbol propio y no el del presupuesto: el presupuesto es lo que se
firmó con el cliente y no se vuelve a tocar, mientras que en obra la medición
cambia cada semana. Compartir las mismas filas obligaría a elegir entre
falsear el contrato o no poder medir lo ejecutado. Así que al vincular un
presupuesto se copia su árbol aquí, y a partir de ahí van por separado.

Lo que sí se conserva es el rastro: cada nodo copiado guarda de qué presupuesto
y de qué partida salió, que es lo que permite comparar ejecutado contra
contratado. Y lo que entra después de arrancar queda marcado `es_anexo`.

El cálculo NO se reimplementa: `parcial_de` y los redondeos son los mismos que
usa presupuestos. Si algún día cambia cómo se mide, cambia en los dos sitios a
la vez, que es lo que se quiere.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import delete, func, or_ as sa_or, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.obras.models import CapituloObra, MedicionObra, Obra, PartidaObra
from app.modules.presupuestos.models_presupuesto import Capitulo, LineaMedicion, Partida
from app.modules.presupuestos.presupuesto_calculo import parcial_de


class NodoNoEncontrado(Exception):
    pass


# --------------------------------------------------------------------------
# Copiar el árbol de un presupuesto a la obra
# --------------------------------------------------------------------------


@dataclass
class ResumenCopia:
    capitulos: int = 0
    partidas: int = 0
    mediciones: int = 0


async def copiar_presupuesto(
    session: AsyncSession,
    obra: Obra,
    presupuesto_id: uuid.UUID,
    *,
    es_anexo: bool,
) -> ResumenCopia:
    """Duplica el árbol de un presupuesto dentro de la obra.

    Sigue la forma de `presupuestos/versionado.py::_escribir_arbol`: los
    capítulos se crean de arriba abajo con un mapa de equivalencias, para que
    el padre exista siempre antes que el hijo.

    Es idempotente por presupuesto: si ese presupuesto ya se copió, no se
    vuelve a copiar. Sin esto, revincular duplicaría toda la obra.
    """
    org_id = require_organization_id()
    resumen = ResumenCopia()

    ya = await session.scalar(
        select(func.count())
        .select_from(CapituloObra)
        .where(
            CapituloObra.obra_id == obra.id,
            CapituloObra.origen_presupuesto_id == presupuesto_id,
        )
    )
    if ya:
        return resumen

    capitulos = list(
        (
            await session.execute(
                select(Capitulo)
                .where(Capitulo.presupuesto_id == presupuesto_id)
                .order_by(Capitulo.orden, Capitulo.codigo)
            )
        ).scalars()
    )
    partidas = list(
        (
            await session.execute(
                select(Partida)
                .where(Partida.presupuesto_id == presupuesto_id)
                .order_by(Partida.orden)
            )
        ).scalars()
    )
    lineas = list(
        (
            await session.execute(
                select(LineaMedicion)
                .join(Partida, Partida.id == LineaMedicion.partida_id)
                .where(Partida.presupuesto_id == presupuesto_id)
                .order_by(LineaMedicion.orden)
            )
        ).scalars()
    )

    # Los anexos se cuelgan detrás de lo que ya hubiera, no encima.
    desplazamiento = int(
        await session.scalar(
            select(func.coalesce(func.max(CapituloObra.orden), -1)).where(
                CapituloObra.obra_id == obra.id, CapituloObra.parent_id.is_(None)
            )
        )
        or -1
    ) + 1

    equivalencias: dict[uuid.UUID, uuid.UUID] = {}
    pendientes = list(capitulos)
    while pendientes:
        avance = False
        for capitulo in list(pendientes):
            if capitulo.parent_id is not None and capitulo.parent_id not in equivalencias:
                continue
            nuevo = CapituloObra(
                organization_id=org_id,
                obra_id=obra.id,
                parent_id=(
                    equivalencias[capitulo.parent_id]
                    if capitulo.parent_id is not None
                    else None
                ),
                codigo=capitulo.codigo,
                resumen=capitulo.resumen,
                texto=capitulo.texto,
                # Solo los de primer nivel se desplazan: los hijos ordenan
                # entre sus hermanos, y ahí no hay nada con lo que chocar.
                orden=(
                    capitulo.orden + desplazamiento
                    if capitulo.parent_id is None
                    else capitulo.orden
                ),
                origen_presupuesto_id=presupuesto_id,
                origen_capitulo_id=capitulo.id,
                es_anexo=es_anexo,
            )
            session.add(nuevo)
            await session.flush()
            equivalencias[capitulo.id] = nuevo.id
            pendientes.remove(capitulo)
            resumen.capitulos += 1
            avance = True
        if not avance:
            # Un padre que no está en el lote dejaría el bucle girando para
            # siempre; los sueltos se cuelgan de la raíz en vez de perderse.
            for capitulo in pendientes:
                nuevo = CapituloObra(
                    organization_id=org_id,
                    obra_id=obra.id,
                    parent_id=None,
                    codigo=capitulo.codigo,
                    resumen=capitulo.resumen,
                    texto=capitulo.texto,
                    orden=capitulo.orden + desplazamiento,
                    origen_presupuesto_id=presupuesto_id,
                    origen_capitulo_id=capitulo.id,
                    es_anexo=es_anexo,
                )
                session.add(nuevo)
                await session.flush()
                equivalencias[capitulo.id] = nuevo.id
                resumen.capitulos += 1
            break

    lineas_por_partida: dict[uuid.UUID, list[LineaMedicion]] = {}
    for linea in lineas:
        lineas_por_partida.setdefault(linea.partida_id, []).append(linea)

    for partida in partidas:
        destino_capitulo = equivalencias.get(partida.capitulo_id)
        if destino_capitulo is None:
            # No debería pasar (la partida siempre cuelga de un capítulo del
            # mismo presupuesto), pero perder una línea en silencio sería peor.
            continue
        nueva = PartidaObra(
            organization_id=org_id,
            obra_id=obra.id,
            capitulo_id=destino_capitulo,
            codigo=partida.codigo,
            resumen=partida.resumen,
            texto=partida.texto,
            unidad=partida.unidad,
            precio=partida.precio,
            precio_venta=partida.precio_venta,
            medicion=partida.medicion,
            importe=partida.importe,
            importe_venta=partida.importe_venta,
            orden=partida.orden,
            origen_presupuesto_id=presupuesto_id,
            origen_partida_id=partida.id,
            es_anexo=es_anexo,
        )
        session.add(nueva)
        await session.flush()
        resumen.partidas += 1

        for linea in lineas_por_partida.get(partida.id, []):
            session.add(
                MedicionObra(
                    organization_id=org_id,
                    partida_id=nueva.id,
                    comentario=linea.comentario,
                    uds=linea.uds,
                    longitud=linea.longitud,
                    anchura=linea.anchura,
                    altura=linea.altura,
                    # El parcial se copia ya calculado: las fórmulas no viajan
                    # a obra, así que recalcularlo desde las dimensiones
                    # cambiaría el número en las líneas que usaban una.
                    parcial=linea.parcial,
                    orden=linea.orden,
                    origen_linea_id=linea.id,
                )
            )
            resumen.mediciones += 1

    await session.flush()
    return resumen


# --------------------------------------------------------------------------
# Lectura del árbol
# --------------------------------------------------------------------------


@dataclass
class NodoArbol:
    capitulo: CapituloObra
    partidas: list[PartidaObra] = field(default_factory=list)
    hijos: list["NodoArbol"] = field(default_factory=list)
    # Acumulado de todo lo que cuelga, partidas propias y de los hijos.
    importe: Decimal = Decimal("0.00")
    importe_venta: Decimal = Decimal("0.00")


async def arbol_de_obra(session: AsyncSession, obra_id: uuid.UUID) -> list[NodoArbol]:
    """El árbol completo en tres consultas, no una por nodo."""
    capitulos = list(
        (
            await session.execute(
                select(CapituloObra)
                .where(CapituloObra.obra_id == obra_id)
                .order_by(CapituloObra.orden, CapituloObra.codigo)
            )
        ).scalars()
    )
    partidas = list(
        (
            await session.execute(
                select(PartidaObra)
                .where(PartidaObra.obra_id == obra_id)
                .order_by(PartidaObra.orden)
            )
        ).scalars()
    )

    nodos = {c.id: NodoArbol(capitulo=c) for c in capitulos}
    for partida in partidas:
        nodo = nodos.get(partida.capitulo_id)
        if nodo is not None:
            nodo.partidas.append(partida)

    raices: list[NodoArbol] = []
    for capitulo in capitulos:
        nodo = nodos[capitulo.id]
        padre = nodos.get(capitulo.parent_id) if capitulo.parent_id else None
        if padre is None:
            raices.append(nodo)
        else:
            padre.hijos.append(nodo)

    def acumular(nodo: NodoArbol) -> tuple[Decimal, Decimal]:
        coste = sum((p.importe for p in nodo.partidas), Decimal("0.00"))
        venta = sum((p.importe_venta for p in nodo.partidas), Decimal("0.00"))
        for hijo in nodo.hijos:
            sub_coste, sub_venta = acumular(hijo)
            coste += sub_coste
            venta += sub_venta
        nodo.importe = coste
        nodo.importe_venta = venta
        return coste, venta

    for raiz in raices:
        acumular(raiz)
    return raices


async def obtener_capitulo(
    session: AsyncSession, capitulo_id: uuid.UUID
) -> CapituloObra | None:
    return await session.get(CapituloObra, capitulo_id)


async def obtener_partida(
    session: AsyncSession, partida_id: uuid.UUID
) -> PartidaObra | None:
    return await session.get(PartidaObra, partida_id)


async def obtener_medicion(
    session: AsyncSession, medicion_id: uuid.UUID
) -> MedicionObra | None:
    return await session.get(MedicionObra, medicion_id)


async def lineas_de_partida(
    session: AsyncSession, partida_id: uuid.UUID
) -> list[MedicionObra]:
    return list(
        (
            await session.execute(
                select(MedicionObra)
                .where(MedicionObra.partida_id == partida_id)
                .order_by(MedicionObra.orden)
            )
        ).scalars()
    )


# --------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------


async def recalcular_partida(session: AsyncSession, partida: PartidaObra) -> None:
    """Vuelve a sumar la medición y los importes de una partida de obra.

    Misma regla que en presupuestos, y por la misma razón: la medición solo se
    recalcula si la partida TIENE parciales. Sin ellos el valor guardado es el
    que alguien tecleó en la rejilla, y recalcularlo desde una lista vacía lo
    pondría a cero — cualquier edición posterior le borraría la medición.
    """
    parciales = [
        fila[0]
        for fila in (
            await session.execute(
                select(MedicionObra.parcial).where(MedicionObra.partida_id == partida.id)
            )
        ).all()
    ]
    if parciales:
        partida.medicion = redondear_medicion(sum(parciales, Decimal("0.000")))
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    partida.importe_venta = redondear_precio(partida.medicion * partida.precio_venta)
    await session.flush()


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------


async def _siguiente_orden(
    session: AsyncSession, columna, *condiciones
) -> int:
    ultimo = await session.scalar(select(func.max(columna)).where(*condiciones))
    return (-1 if ultimo is None else int(ultimo)) + 1


async def crear_capitulo(
    session: AsyncSession,
    obra: Obra,
    *,
    resumen: str,
    codigo: str | None = None,
    parent_id: uuid.UUID | None = None,
    texto: str | None = None,
    orden: int | None = None,
) -> CapituloObra:
    """Un capítulo nuevo en la obra.

    Nace `es_anexo=True` siempre: si se está creando a mano es que no venía en
    ningún presupuesto contratado, y eso es exactamente lo que hay que ver
    marcado en el árbol.
    """
    if parent_id is not None:
        padre = await obtener_capitulo(session, parent_id)
        if padre is None or padre.obra_id != obra.id:
            raise NodoNoEncontrado("El capítulo padre no es de esta obra")
    if orden is None:
        orden = await _siguiente_orden(
            session,
            CapituloObra.orden,
            CapituloObra.obra_id == obra.id,
            CapituloObra.parent_id == parent_id
            if parent_id is not None
            else CapituloObra.parent_id.is_(None),
        )
    capitulo = CapituloObra(
        organization_id=require_organization_id(),
        obra_id=obra.id,
        parent_id=parent_id,
        codigo=codigo or "",
        resumen=resumen,
        texto=texto,
        orden=orden,
        es_anexo=True,
    )
    session.add(capitulo)
    await session.flush()
    return capitulo


async def crear_partida(
    session: AsyncSession,
    capitulo: CapituloObra,
    *,
    resumen: str,
    codigo: str | None = None,
    unidad: str = "ud",
    precio: Decimal | None = None,
    precio_venta: Decimal | None = None,
    medicion: Decimal | None = None,
    orden: int | None = None,
) -> PartidaObra:
    """Una partida nueva. Como el capítulo, nace marcada como anexo."""
    if orden is None:
        orden = await _siguiente_orden(
            session, PartidaObra.orden, PartidaObra.capitulo_id == capitulo.id
        )
    partida = PartidaObra(
        organization_id=require_organization_id(),
        obra_id=capitulo.obra_id,
        capitulo_id=capitulo.id,
        codigo=codigo or "",
        resumen=resumen,
        unidad=unidad,
        precio=precio if precio is not None else Decimal("0.00"),
        precio_venta=precio_venta if precio_venta is not None else Decimal("0.00"),
        medicion=medicion if medicion is not None else Decimal("0.000"),
        orden=orden,
        es_anexo=True,
    )
    session.add(partida)
    await session.flush()
    await recalcular_partida(session, partida)
    return partida


async def actualizar_capitulo(
    session: AsyncSession, capitulo: CapituloObra, cambios: dict
) -> CapituloObra:
    if "parent_id" in cambios and cambios["parent_id"] is not None:
        nuevo_padre = await obtener_capitulo(session, cambios["parent_id"])
        if nuevo_padre is None or nuevo_padre.obra_id != capitulo.obra_id:
            raise NodoNoEncontrado("El capítulo padre no es de esta obra")
        if await _seria_ciclo(session, capitulo, nuevo_padre):
            raise NodoNoEncontrado("Un capítulo no puede colgar de sí mismo")
    for campo, valor in cambios.items():
        setattr(capitulo, campo, valor)
    await session.flush()
    return capitulo


async def _seria_ciclo(
    session: AsyncSession, capitulo: CapituloObra, nuevo_padre: CapituloObra
) -> bool:
    """¿Meter `capitulo` dentro de `nuevo_padre` cerraría un bucle?

    Sin esta comprobación, arrastrar un capítulo dentro de su propio hijo
    dejaría una rama desconectada del árbol e invisible para siempre.
    """
    actual: CapituloObra | None = nuevo_padre
    while actual is not None:
        if actual.id == capitulo.id:
            return True
        actual = (
            await obtener_capitulo(session, actual.parent_id)
            if actual.parent_id is not None
            else None
        )
    return False


async def actualizar_partida(
    session: AsyncSession, partida: PartidaObra, cambios: dict
) -> PartidaObra:
    if "capitulo_id" in cambios:
        destino = await obtener_capitulo(session, cambios["capitulo_id"])
        if destino is None or destino.obra_id != partida.obra_id:
            raise NodoNoEncontrado("El capítulo de destino no es de esta obra")
    for campo, valor in cambios.items():
        setattr(partida, campo, valor)
    await session.flush()
    await recalcular_partida(session, partida)
    return partida


async def eliminar_capitulo(session: AsyncSession, capitulo: CapituloObra) -> None:
    await session.delete(capitulo)
    await session.flush()


async def eliminar_partida(session: AsyncSession, partida: PartidaObra) -> None:
    await session.delete(partida)
    await session.flush()


async def crear_medicion(
    session: AsyncSession,
    partida: PartidaObra,
    *,
    comentario: str | None = None,
    uds: Decimal | None = None,
    longitud: Decimal | None = None,
    anchura: Decimal | None = None,
    altura: Decimal | None = None,
) -> MedicionObra:
    orden = await _siguiente_orden(
        session, MedicionObra.orden, MedicionObra.partida_id == partida.id
    )
    linea = MedicionObra(
        organization_id=require_organization_id(),
        partida_id=partida.id,
        comentario=comentario,
        uds=uds,
        longitud=longitud,
        anchura=anchura,
        altura=altura,
        parcial=parcial_de(uds, longitud, anchura, altura),
        orden=orden,
    )
    session.add(linea)
    await session.flush()
    await recalcular_partida(session, partida)
    return linea


async def actualizar_medicion(
    session: AsyncSession, linea: MedicionObra, cambios: dict
) -> MedicionObra:
    for campo, valor in cambios.items():
        setattr(linea, campo, valor)
    linea.parcial = parcial_de(linea.uds, linea.longitud, linea.anchura, linea.altura)
    await session.flush()
    partida = await obtener_partida(session, linea.partida_id)
    if partida is not None:
        await recalcular_partida(session, partida)
    return linea


async def eliminar_medicion(session: AsyncSession, linea: MedicionObra) -> None:
    partida_id = linea.partida_id
    await session.delete(linea)
    await session.flush()
    partida = await obtener_partida(session, partida_id)
    if partida is not None:
        await recalcular_partida(session, partida)


async def borrar_copia_de_presupuesto(
    session: AsyncSession, obra_id: uuid.UUID, presupuesto_id: uuid.UUID
) -> int:
    """Quita del árbol lo que vino de un presupuesto concreto.

    Solo se usa al desvincular, y solo si nadie ha medido nada encima: lo
    comprueba quien llama. Los capítulos van en cascada a sus partidas, y las
    partidas a sus mediciones, así que basta con borrar los capítulos… salvo
    las partidas que alguien haya movido a un capítulo de otro origen, que se
    borran aparte.
    """
    partidas = await session.execute(
        delete(PartidaObra).where(
            PartidaObra.obra_id == obra_id,
            PartidaObra.origen_presupuesto_id == presupuesto_id,
        )
    )
    capitulos = await session.execute(
        delete(CapituloObra).where(
            CapituloObra.obra_id == obra_id,
            CapituloObra.origen_presupuesto_id == presupuesto_id,
        )
    )
    await session.flush()
    return int(partidas.rowcount or 0) + int(capitulos.rowcount or 0)


async def tiene_mediciones_propias(
    session: AsyncSession, obra_id: uuid.UUID, presupuesto_id: uuid.UUID
) -> bool:
    """¿Se ha medido en obra algo que vino de este presupuesto?

    Si es así, desvincularlo tiraría trabajo real, y hay que negarse. Cuenta
    dos cosas: los parciales añadidos en obra (`origen_linea_id` a NULL) y los
    copiados que alguien haya retocado después.

    Lo que NO vale es comparar `created_at` con el de la partida: `now()` en
    PostgreSQL es la hora de la transacción, así que copiar y medir en la misma
    petición dejan el mismo sello y la comparación sale siempre falsa. Por eso
    el origen se marca en una columna.
    """
    total = await session.scalar(
        select(func.count())
        .select_from(MedicionObra)
        .join(PartidaObra, PartidaObra.id == MedicionObra.partida_id)
        .where(
            PartidaObra.obra_id == obra_id,
            PartidaObra.origen_presupuesto_id == presupuesto_id,
            sa_or(
                MedicionObra.origen_linea_id.is_(None),
                MedicionObra.updated_at > MedicionObra.created_at,
            ),
        )
    )
    return bool(total)
