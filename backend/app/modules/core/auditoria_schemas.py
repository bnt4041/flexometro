import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.core.auditoria_models import AccionAuditoria


class CambioCampoOut(BaseModel):
    campo: str
    antes: object | None
    despues: object | None


class RegistroAuditoriaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    accion: AccionAuditoria
    cambios: list[CambioCampoOut] | None
    descripcion: str | None
    usuario_subject: str | None
    usuario_nombre: str | None
    created_at: datetime
