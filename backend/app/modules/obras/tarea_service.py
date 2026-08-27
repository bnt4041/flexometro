"""Gestor de tareas de obra: lista con estados y tablero kanban.

Lo único con algo de fondo aquí es el reordenado al arrastrar una tarjeta. El
`orden` de una tarea es su posición DENTRO de su columna, no dentro de la obra:
mover una tarjeta cambia estado y orden a la vez, y hay que recolocar a sus
vecinas para que no queden dos con el mismo número.
"""

import uuid
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.obras.models import EstadoTarea, Obra, Personal, PrioridadTarea, Tarea


class TareaInvalida(Exception):
    pass


# El orden de las columnas del tablero, para poder ordenar en SQL.
_ORDEN_COLUMNA = case(
    (Tarea.estado == EstadoTarea.PENDIENTE, 0),
    (Tarea.estado == EstadoTarea.EN_CURSO, 1),
    else_=2,
)


async def _validar_responsable(
    session: AsyncSession, responsable_id: uuid.UUID | None
) -> None:
    if responsable_id is None:
        return
    org_id = require_organization_id()
    existe = await session.scalar(
        select(Personal.id).where(
            Personal.id == responsable_id, Personal.organization_id == org_id
        )
    )
    if existe is None:
        raise TareaInvalida("El responsable no existe en esta organización")


async def crear(
    session: AsyncSession,
    obra: Obra,
    *,
    titulo: str,
    descripcion: str | None = None,
    responsable_id: uuid.UUID | None = None,
    fecha_limite: date | None = None,
    estado: EstadoTarea = EstadoTarea.PENDIENTE,
    prioridad: PrioridadTarea = PrioridadTarea.NORMAL,
) -> Tarea:
    limpio = titulo.strip()
    if not limpio:
        raise TareaInvalida("La tarea necesita un título")
    await _validar_responsable(session, responsable_id)

    # Al final de su columna: lo nuevo se añade abajo, que es donde se busca.
    ultimo = await session.scalar(
        select(func.max(Tarea.orden)).where(
            Tarea.obra_id == obra.id, Tarea.estado == estado
        )
    )
    tarea = Tarea(
        organization_id=require_organization_id(),
        obra_id=obra.id,
        titulo=limpio,
        descripcion=descripcion,
        responsable_id=responsable_id,
        fecha_limite=fecha_limite,
        estado=estado,
        prioridad=prioridad,
        orden=(-1 if ultimo is None else int(ultimo)) + 1,
        completada_en=date.today() if estado == EstadoTarea.HECHA else None,
        **datos_autoria(),
    )
    session.add(tarea)
    await session.flush()
    return tarea


async def listar(
    session: AsyncSession,
    obra_id: uuid.UUID,
    *,
    estado: EstadoTarea | None = None,
) -> list[Tarea]:
    """Las tareas de la obra ordenadas como se pintan: por columna y posición.

    Las hechas van al final del todo aunque su columna sea la tercera, para que
    la lista plana se lea de lo pendiente a lo cerrado.
    """
    consulta = select(Tarea).where(Tarea.obra_id == obra_id)
    if estado is not None:
        consulta = consulta.where(Tarea.estado == estado)
    filas = (
        await session.execute(
            # El estado NO se puede ordenar por su valor: el enum se guarda como
            # texto y alfabéticamente sale «en_curso, hecha, pendiente», que no
            # es el orden del tablero. Hace falta el orden explícito.
            consulta.order_by(_ORDEN_COLUMNA, Tarea.orden)
        )
    ).scalars()
    return list(filas)


async def obtener(session: AsyncSession, tarea_id: uuid.UUID) -> Tarea | None:
    return await session.get(Tarea, tarea_id)


async def actualizar(session: AsyncSession, tarea: Tarea, cambios: dict) -> Tarea:
    if "titulo" in cambios:
        limpio = (cambios["titulo"] or "").strip()
        if not limpio:
            raise TareaInvalida("La tarea necesita un título")
        cambios["titulo"] = limpio
    if "responsable_id" in cambios:
        await _validar_responsable(session, cambios["responsable_id"])

    estado_nuevo = cambios.get("estado")
    for campo, valor in cambios.items():
        setattr(tarea, campo, valor)

    # La fecha de cierre se pone y se quita con el estado, salvo que quien
    # llama la haya dado a mano (mover una tarjeta no la manda).
    if estado_nuevo is not None and "completada_en" not in cambios:
        if estado_nuevo == EstadoTarea.HECHA:
            if tarea.completada_en is None:
                tarea.completada_en = date.today()
        else:
            tarea.completada_en = None

    await session.flush()
    return tarea


async def mover(
    session: AsyncSession,
    tarea: Tarea,
    *,
    estado: EstadoTarea,
    posicion: int,
) -> Tarea:
    """Suelta una tarjeta en una columna y una posición.

    Se renumeran las dos columnas implicadas de 0 en adelante. Es más trabajo
    que un solo UPDATE, pero deja el orden sin huecos ni empates: con `orden`
    repetido el tablero pinta las tarjetas en un orden que cambia entre
    recargas, y eso es de lo más difícil de diagnosticar después.
    """
    origen = tarea.estado
    hermanas = list(
        (
            await session.execute(
                select(Tarea)
                .where(
                    Tarea.obra_id == tarea.obra_id,
                    Tarea.estado == estado,
                    Tarea.id != tarea.id,
                )
                .order_by(Tarea.orden)
            )
        ).scalars()
    )
    # `posicion` viene del cliente; se recorta al hueco real en vez de fallar.
    destino = max(0, min(posicion, len(hermanas)))
    hermanas.insert(destino, tarea)

    tarea.estado = estado
    if estado == EstadoTarea.HECHA:
        if tarea.completada_en is None:
            tarea.completada_en = date.today()
    else:
        tarea.completada_en = None

    for indice, hermana in enumerate(hermanas):
        hermana.orden = indice

    if origen != estado:
        # La columna de la que sale se cierra: si no, quedan huecos que van
        # creciendo con cada movimiento.
        quedan = list(
            (
                await session.execute(
                    select(Tarea)
                    .where(
                        Tarea.obra_id == tarea.obra_id,
                        Tarea.estado == origen,
                        Tarea.id != tarea.id,
                    )
                    .order_by(Tarea.orden)
                )
            ).scalars()
        )
        for indice, hermana in enumerate(quedan):
            hermana.orden = indice

    await session.flush()
    return tarea


async def eliminar(session: AsyncSession, tarea: Tarea) -> None:
    await session.delete(tarea)
    await session.flush()


async def resumen_de_obra(session: AsyncSession, obra_id: uuid.UUID) -> dict:
    """Cuántas tareas hay en cada estado y cuántas van con retraso.

    Lo usa el widget del cuadro de mandos. Una tarea vencida es la que tiene
    fecha límite pasada y no está hecha: una hecha tarde ya no pide nada.
    """
    hoy = date.today()
    filas = (
        await session.execute(
            select(Tarea.estado, func.count())
            .where(Tarea.obra_id == obra_id)
            .group_by(Tarea.estado)
        )
    ).all()
    por_estado = {estado: int(n) for estado, n in filas}

    vencidas = await session.scalar(
        select(func.count())
        .select_from(Tarea)
        .where(
            Tarea.obra_id == obra_id,
            Tarea.estado != EstadoTarea.HECHA,
            Tarea.fecha_limite.is_not(None),
            Tarea.fecha_limite < hoy,
        )
    )
    return {
        "pendientes": por_estado.get(EstadoTarea.PENDIENTE, 0),
        "en_curso": por_estado.get(EstadoTarea.EN_CURSO, 0),
        "hechas": por_estado.get(EstadoTarea.HECHA, 0),
        "vencidas": int(vencidas or 0),
    }
