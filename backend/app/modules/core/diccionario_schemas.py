import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.core.diccionario_models import TipoDiccionario


class EntradaDiccionarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: TipoDiccionario
    clave: str
    etiqueta: str
    valor: Decimal | None
    activo: bool
    orden: int


class EntradaDiccionarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clave: str = Field(min_length=1, max_length=64)
    etiqueta: str = Field(min_length=1, max_length=120)
    valor: Decimal | None = Field(default=None, ge=0, le=100)
    orden: int = 0


class EntradaDiccionarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etiqueta: str | None = Field(default=None, min_length=1, max_length=120)
    valor: Decimal | None = Field(default=None, ge=0, le=100)
    activo: bool | None = None
    orden: int | None = None
