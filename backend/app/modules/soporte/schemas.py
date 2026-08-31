import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.soporte.enums import EstadoTicket, Prioridad, TipoTicket


class MensajeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cuerpo: str
    interno: bool
    de_ia: bool
    creado_por_nombre: str | None = None
    created_at: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    titulo: str
    descripcion: str
    tipo: TipoTicket
    estado: EstadoTicket
    prioridad: Prioridad
    asignado_a_nombre: str | None = None
    ruta_origen: str | None = None
    creado_por_nombre: str | None = None
    created_at: datetime
    mensajes: list[MensajeOut] = []


class TicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = Field(min_length=1)
    tipo: TipoTicket = TipoTicket.PETICION
    prioridad: Prioridad = Prioridad.NORMAL
    #: Dónde estaba el usuario. Lo rellena el widget solo.
    ruta_origen: str | None = Field(default=None, max_length=400)


class TicketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: EstadoTicket | None = None
    prioridad: Prioridad | None = None
    asignado_a_subject: str | None = None
    asignado_a_nombre: str | None = None


class MensajeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cuerpo: str = Field(min_length=1)
    interno: bool = False


class PaginaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    titulo: str
    contenido: str
    categoria: str | None = None
    publicada: bool
    version: int
    indexada_en: datetime | None = None
    updated_at: datetime
    #: `False` si se ha editado después de indexarla: el asistente todavía
    #: responde con la versión anterior.
    indice_al_dia: bool = True


class PaginaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(min_length=1, max_length=200)
    contenido: str = ""
    categoria: str | None = Field(default=None, max_length=80)
    publicada: bool = True


class ResultadoBusqueda(BaseModel):
    titulo: str
    texto: str
    origen: str
    origen_id: str
    distancia: float
