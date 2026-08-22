import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PlantillaPresupuestoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    es_sistema: bool
    nombre: str
    claves_detectadas: list[str]
    activo: bool
    created_at: datetime


FormatoDescarga = Literal["docx", "pdf"]
