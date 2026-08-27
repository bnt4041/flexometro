import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_principal
from app.core.database import get_session
from app.modules.core import notificaciones_service as service

router = APIRouter(
    prefix="/notificaciones", tags=["core"], dependencies=[Depends(get_principal)]
)


class NotificacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    titulo: str
    cuerpo: str | None
    enlace: str | None
    importante: bool
    leida_en: datetime | None
    resuelta_en: datetime | None
    presupuesto_id: uuid.UUID | None
    enviada_en: datetime | None
    created_at: datetime
    # `token_acceso` NO sale nunca: es el enlace del proveedor, y quien acepta
    # la solicitud no necesita verlo — lo usa el servidor por él.


class ContadorOut(BaseModel):
    pendientes: int


class MarcarLeidasIn(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


class AceptadaOut(BaseModel):
    presupuesto_id: uuid.UUID
    mensaje: str


class DevueltaOut(BaseModel):
    lineas: int
    mensaje: str


@router.get("", response_model=list[NotificacionOut])
async def listar(
    solo_pendientes: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[NotificacionOut]:
    filas = await service.listar(session, solo_pendientes=solo_pendientes)
    return [NotificacionOut.model_validate(f) for f in filas]


@router.get("/contador", response_model=ContadorOut)
async def contador(session: AsyncSession = Depends(get_session)) -> ContadorOut:
    """Lo sondea la campana de la barra superior: barato a propósito, solo un
    COUNT — no hay WebSocket ni SSE en el proyecto."""
    return ContadorOut(pendientes=await service.contar_pendientes(session))


@router.get("/por-presupuesto/{presupuesto_id}", response_model=NotificacionOut | None)
async def por_presupuesto(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> NotificacionOut | None:
    """Si este presupuesto salió de una solicitud de otra empresa, devuelve su
    aviso — para poder devolverle la oferta desde la propia ficha."""
    fila = await service.por_presupuesto(session, presupuesto_id)
    return NotificacionOut.model_validate(fila) if fila else None


@router.post("/leidas", response_model=ContadorOut)
async def marcar_leidas(
    datos: MarcarLeidasIn,
    session: AsyncSession = Depends(get_session),
) -> ContadorOut:
    await service.marcar_leidas(session, datos.ids)
    pendientes = await service.contar_pendientes(session)
    await session.commit()
    return ContadorOut(pendientes=pendientes)


@router.post("/{notificacion_id}/aceptar", response_model=AceptadaOut)
async def aceptar(
    notificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AceptadaOut:
    """Acepta una solicitud de precios que llega de otra cuenta: la copia como
    un presupuesto propio, en mi organización."""
    try:
        notificacion = await service.obtener(session, notificacion_id)
        presupuesto = await service.aceptar_solicitud(session, notificacion)
    except service.NotificacionNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (service.NotificacionSinAccion, service.SolicitudNoDisponible) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return AceptadaOut(
        presupuesto_id=presupuesto.id,
        mensaje=f"Creado el presupuesto «{presupuesto.nombre}» con las partidas de la solicitud.",
    )


@router.post("/{notificacion_id}/devolver", response_model=DevueltaOut)
async def devolver(
    notificacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> DevueltaOut:
    """Manda al emisor los precios del presupuesto que se preparó al aceptar,
    para que entren en su comparativo."""
    try:
        notificacion = await service.obtener(session, notificacion_id)
        lineas = await service.devolver_oferta(session, notificacion)
    except service.NotificacionNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        service.NotificacionSinAccion,
        service.SolicitudNoDisponible,
        service.OfertaSinPrecios,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return DevueltaOut(
        lineas=lineas,
        mensaje=f"Oferta enviada con {lineas} precio{'s' if lineas != 1 else ''}.",
    )
