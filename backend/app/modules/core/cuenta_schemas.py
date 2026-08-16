import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CuentaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    is_active: bool
    tarifa_id: uuid.UUID | None
    compartir_maestros: bool
    created_at: datetime


class CuentaDetalle(CuentaOut):
    settings: dict
    # Aviso (no bloqueo) para la pantalla de patrones de numeración: si sus
    # organizaciones tienen CIF distinto, compartir secuencia entre ellas
    # puede incumplir la correlatividad exigida a cada empresa por separado.
    cifs_distintos: bool


class CuentaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)


class CuentaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    tarifa_id: uuid.UUID | None = None
    compartir_maestros: bool | None = None


class PatronNumeracionOut(BaseModel):
    tipo_documento: str
    patron: str
    secuencia_compartida: bool


class PatronNumeracionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patron: str = Field(min_length=1, max_length=80)
    secuencia_compartida: bool = False
