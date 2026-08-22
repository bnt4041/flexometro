import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.html_seguro import sanear_html
from app.modules.crm.models import EntidadNota, TipoNota


class NotaCreate(BaseModel):
    contenido: str = Field(min_length=1)


class AdjuntoNotaOut(BaseModel):
    # `documento_id` nulo: el adjunto se mandó por correo sin guardarlo en la
    # ficha (Fase 42), así que no hay nada que descargar después — se queda
    # solo el nombre, como constancia de qué se envió.
    documento_id: uuid.UUID | None = None
    nombre_archivo: str


class NotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entidad: EntidadNota
    entidad_id: uuid.UUID
    contenido: str
    tipo: TipoNota
    asunto: str | None = None
    destinatario: str | None = None
    adjuntos: list[AdjuntoNotaOut] = Field(default_factory=list)
    created_at: datetime
    creado_por_nombre: str | None = None


class EnviarEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destinatario: EmailStr
    asunto: str = Field(min_length=1, max_length=255)
    cuerpo_html: str = Field(min_length=1)
    documento_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("cuerpo_html")
    @classmethod
    def _sanear_cuerpo(cls, valor: str) -> str:
        return sanear_html(valor) or ""
