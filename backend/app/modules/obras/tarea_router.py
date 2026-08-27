"""Rutas del gestor de tareas de obra."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.modules.obras import service, tarea_service
from app.modules.obras.models import EstadoTarea, Personal, Tarea
from app.modules.obras.schemas import (
    MoverTareaIn,
    ResumenTareasObra,
    TareaCreate,
    TareaOut,
    TareaUpdate,
)

guard = Depends(require_module("obras"))

obra_tareas_router = APIRouter(prefix="/api/obras", tags=["obras"], dependencies=[guard])
tareas_router = APIRouter(prefix="/api/tareas", tags=["obras"], dependencies=[guard])


async def _nombres_de_personal(
    session: AsyncSession, tareas: list[Tarea]
) -> dict[uuid.UUID, str]:
    """`personal_id → nombre`, de una vez para todo el tablero."""
    ids = {t.responsable_id for t in tareas if t.responsable_id is not None}
    if not ids:
        return {}
    filas = (
        await session.execute(
            select(Personal.id, Personal.nombre, Personal.apellidos).where(
                Personal.id.in_(ids)
            )
        )
    ).all()
    return {
        fila[0]: f"{fila[1]} {fila[2]}".strip() if fila[2] else fila[1] for fila in filas
    }


def _salida(tarea: Tarea, nombres: dict[uuid.UUID, str]) -> TareaOut:
    salida = TareaOut.model_validate(tarea)
    salida.responsable_nombre = (
        nombres.get(tarea.responsable_id) if tarea.responsable_id else None
    )
    return salida


@obra_tareas_router.get("/{obra_id}/tareas", response_model=list[TareaOut])
async def listar_tareas(
    obra_id: uuid.UUID,
    estado: EstadoTarea | None = None,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> list[TareaOut]:
    if await service.obtener_obra(session, obra_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    tareas = await tarea_service.listar(session, obra_id, estado=estado)
    nombres = await _nombres_de_personal(session, tareas)
    return [_salida(t, nombres) for t in tareas]


@obra_tareas_router.get("/{obra_id}/tareas/resumen", response_model=ResumenTareasObra)
async def resumen_de_tareas(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> ResumenTareasObra:
    if await service.obtener_obra(session, obra_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    return ResumenTareasObra(**await tarea_service.resumen_de_obra(session, obra_id))


@obra_tareas_router.post(
    "/{obra_id}/tareas", response_model=TareaOut, status_code=status.HTTP_201_CREATED
)
async def crear_tarea(
    obra_id: uuid.UUID,
    datos: TareaCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> TareaOut:
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    try:
        tarea = await tarea_service.crear(
            session,
            obra,
            titulo=datos.titulo,
            descripcion=datos.descripcion,
            responsable_id=datos.responsable_id,
            fecha_limite=datos.fecha_limite,
            estado=datos.estado,
            prioridad=datos.prioridad,
        )
    except tarea_service.TareaInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    nombres = await _nombres_de_personal(session, [tarea])
    salida = _salida(tarea, nombres)
    await session.commit()
    return salida


async def _tarea_o_404(session: AsyncSession, tarea_id: uuid.UUID) -> Tarea:
    tarea = await tarea_service.obtener(session, tarea_id)
    if tarea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
    return tarea


@tareas_router.patch("/{tarea_id}", response_model=TareaOut)
async def actualizar_tarea(
    tarea_id: uuid.UUID,
    datos: TareaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> TareaOut:
    tarea = await _tarea_o_404(session, tarea_id)
    verificar_propiedad(alcance, principal, tarea.creado_por_subject)
    try:
        await tarea_service.actualizar(
            session, tarea, datos.model_dump(exclude_unset=True)
        )
    except tarea_service.TareaInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    nombres = await _nombres_de_personal(session, [tarea])
    salida = _salida(tarea, nombres)
    await session.commit()
    return salida


@tareas_router.post("/{tarea_id}/mover", response_model=TareaOut)
async def mover_tarea(
    tarea_id: uuid.UUID,
    datos: MoverTareaIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> TareaOut:
    """Lo que llama el tablero al soltar una tarjeta: columna y posición."""
    tarea = await _tarea_o_404(session, tarea_id)
    verificar_propiedad(alcance, principal, tarea.creado_por_subject)
    await tarea_service.mover(
        session, tarea, estado=datos.estado, posicion=datos.posicion
    )
    nombres = await _nombres_de_personal(session, [tarea])
    salida = _salida(tarea, nombres)
    await session.commit()
    return salida


@tareas_router.delete("/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_tarea(
    tarea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> None:
    tarea = await _tarea_o_404(session, tarea_id)
    verificar_propiedad(alcance, principal, tarea.creado_por_subject)
    await tarea_service.eliminar(session, tarea)
    await session.commit()


router = APIRouter()
router.include_router(obra_tareas_router)
router.include_router(tareas_router)
