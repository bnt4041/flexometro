import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.plexo.enums import EstadoVinculo


class PerfilOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    visible: bool
    activado_en: datetime | None = None


class PerfilIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible: bool


class OrganizacionPublicaOut(BaseModel):
    """Lo mínimo de una organización que se puede enseñar fuera de ella: ni
    slug interno, ni nada que no sea lo que pondría en una tarjeta de
    visita."""

    id: uuid.UUID
    name: str
    cif: str | None = None


class VinculoOut(BaseModel):
    id: uuid.UUID
    estado: EstadoVinculo
    mensaje: str | None = None
    #: La OTRA organización del vínculo, resuelta ya según si el que mira es
    #: el origen o el destino — la pantalla no tiene que saber cuál de las
    #: dos es "la suya".
    otra_organizacion: OrganizacionPublicaOut
    #: `True` si el que mira es quien invitó. Decide qué botones tiene
    #: sentido enseñar (no se puede aceptar tu propia invitación).
    soy_quien_invito: bool
    invitado_por_nombre: str
    respondido_por_nombre: str | None = None
    created_at: datetime
    respondido_en: datetime | None = None


class InvitarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organizacion_destino_id: uuid.UUID
    mensaje: str | None = Field(default=None, max_length=500)
