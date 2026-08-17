import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.documentos.models import EntidadDocumento


class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entidad: EntidadDocumento
    entidad_id: uuid.UUID
    nombre_archivo: str
    content_type: str
    tamano_bytes: int
    created_at: datetime
    creado_por_nombre: str | None = None
