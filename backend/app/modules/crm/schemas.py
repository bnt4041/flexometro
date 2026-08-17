import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.crm.models import EntidadNota


class NotaCreate(BaseModel):
    contenido: str = Field(min_length=1)


class NotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entidad: EntidadNota
    entidad_id: uuid.UUID
    contenido: str
    created_at: datetime
    creado_por_nombre: str | None = None
