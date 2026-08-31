import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.desarrolladores.enums import EstadoEntrega


class ClaveApiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    #: Los primeros caracteres, para reconocerla. El secreto no vuelve nunca.
    prefijo: str
    ambitos: dict
    activa: bool
    expira_en: datetime | None = None
    ultimo_uso_en: datetime | None = None
    created_at: datetime


class ClaveApiCreada(ClaveApiOut):
    """Lo mismo, más el secreto EN CLARO. Es la única vez que se ve: no se
    guarda, así que no hay forma de volver a enseñarlo."""

    clave: str


class ClaveApiIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    #: `{"obras": {"ver": "todos", "crear": "ninguno", …}}`. Mismo modelo que
    #: los permisos de una persona.
    ambitos: dict = Field(default_factory=dict)
    dias_validez: int | None = Field(default=None, ge=1, le=3650)


class ClaveApiUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    ambitos: dict | None = None
    activa: bool | None = None


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=500)
    eventos: list[str] = Field(min_length=1)
    activa: bool = True


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    url: str
    eventos: list[str]
    activa: bool
    created_at: datetime
    #: El secreto para firmar. Se enseña porque hace falta para verificar al
    #: otro lado, y quien administra el webhook es quien lo configura allí.
    secreto: str


class EntregaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    suscripcion_id: uuid.UUID
    evento: str
    estado: EstadoEntrega
    intentos: int
    proximo_intento_en: datetime | None = None
    entregada_en: datetime | None = None
    respuesta_codigo: int | None = None
    error: str | None = None
    created_at: datetime
