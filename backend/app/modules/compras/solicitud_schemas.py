import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.compras.models import EstadoSolicitud


class SolicitudCrear(BaseModel):
    presupuesto_id: uuid.UUID
    proveedor_id: uuid.UUID
    partida_ids: list[uuid.UUID] = Field(min_length=1)
    fecha_limite: date | None = None
    notas: str | None = Field(default=None, max_length=2000)


class SolicitudActualizar(BaseModel):
    """Todos los campos opcionales: solo se tocan los que el cliente mande
    (`model_dump(exclude_unset=True)` en el router) — así se puede llamar
    para cambiar solo la fecha límite sin arrastrarse las notas por delante."""

    notas: str | None = Field(default=None, max_length=2000)
    fecha_limite: date | None = None


class LineasActualizar(BaseModel):
    partida_ids: list[uuid.UUID] = Field(min_length=1)


class SolicitudLineaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID | None
    capitulo_resumen: str | None
    codigo: str | None
    resumen: str
    unidad: str
    medicion: Decimal
    precio_ofertado: Decimal | None
    observaciones_proveedor: str | None
    aprobada: bool


class SolicitudOut(BaseModel):
    id: uuid.UUID
    codigo: str
    presupuesto_id: uuid.UUID
    proveedor_id: uuid.UUID
    proveedor_razon_social: str
    proveedor_email: str | None = None
    estado: EstadoSolicitud
    fecha_limite: date | None
    enviada_en: datetime | None
    respondida_en: datetime | None
    notas: str | None
    oferta_presupuesto_id: uuid.UUID | None
    lineas: list[SolicitudLineaOut] = Field(default_factory=list)


class SolicitudConEnlaceOut(SolicitudOut):
    """El enlace del proveedor solo existe en claro en el momento de
    emitirlo: aquí viaja una vez, para poder copiarlo, y nunca más."""

    enlace: str


class EnlaceOut(BaseModel):
    enlace: str
