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


class DocumentoBusquedaOut(DocumentoOut):
    """Como `DocumentoOut`, más el código de la ficha de origen — para el
    selector de adjuntos del correo (Fase 42), que busca en toda la cuenta,
    no en una sola ficha."""

    entidad_codigo: str | None = None
