import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.modules.campos_libres.models import TipoCampoLibre


class CampoLibreDefinicionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clave: str
    etiqueta: str
    tipo: TipoCampoLibre
    opciones: list[str]
    requerido: bool
    orden: int
    activo: bool


class CampoLibreDefinicionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clave: str = Field(min_length=1, max_length=64)
    etiqueta: str = Field(min_length=1, max_length=120)
    tipo: TipoCampoLibre = TipoCampoLibre.TEXTO
    opciones: list[str] = Field(default_factory=list)
    requerido: bool = False
    orden: int = 0


class CampoLibreDefinicionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etiqueta: str | None = Field(default=None, min_length=1, max_length=120)
    tipo: TipoCampoLibre | None = None
    opciones: list[str] | None = None
    requerido: bool | None = None
    orden: int | None = None
    activo: bool | None = None


class ValoresCampoLibreUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valores: dict[str, str | None]
