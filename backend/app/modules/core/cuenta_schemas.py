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
    max_organizaciones: int
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
    max_organizaciones: int | None = Field(default=None, ge=1, le=20)


class PatronNumeracionOut(BaseModel):
    tipo_documento: str
    patron: str
    secuencia_compartida: bool


class PatronNumeracionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patron: str = Field(min_length=1, max_length=80)
    secuencia_compartida: bool = False


class EmpresaOut(BaseModel):
    """Datos básicos de una empresa (organización) de la cuenta, autoservicio
    (Fase 40/41) — sin `is_active` ni `modulos`: eso sigue siendo cosa del
    superadmin. Cualquier empresa de la propia cuenta es editable así, no
    solo la activa en la sesión (ver `EmpresaResumenOut`/`es_la_actual`)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    cif: str | None
    direccion: str | None
    codigo_postal: str | None
    ciudad: str | None
    provincia: str | None
    telefono: str | None
    email: str | None
    web: str | None
    linkedin: str | None
    instagram: str | None
    facebook: str | None
    twitter: str | None
    politica_privacidad: str | None
    tiene_logo: bool = False


class EmpresaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    cif: str | None = Field(default=None, max_length=20)
    direccion: str | None = Field(default=None, max_length=255)
    codigo_postal: str | None = Field(default=None, max_length=12)
    ciudad: str | None = Field(default=None, max_length=120)
    provincia: str | None = Field(default=None, max_length=120)
    telefono: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    web: str | None = Field(default=None, max_length=255)
    linkedin: str | None = Field(default=None, max_length=255)
    instagram: str | None = Field(default=None, max_length=255)
    facebook: str | None = Field(default=None, max_length=255)
    twitter: str | None = Field(default=None, max_length=255)
    politica_privacidad: str | None = None


class EmpresaResumenOut(BaseModel):
    """Una fila de la lista de empresas de la cuenta (Fase 41) — no es
    `EmpresaOut`: esa es la ficha completa de la organización ACTIVA, esto es
    solo lo necesario para elegir/reconocer cada una en el listado."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    cif: str | None
    is_active: bool
    es_la_actual: bool = False


class EmpresasCuentaOut(BaseModel):
    empresas: list[EmpresaResumenOut]
    max_organizaciones: int
    puede_crear: bool


class EmpresaCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Sin `slug`: se genera del nombre (Fase 41), ver `service.crear_organizacion`.
    name: str = Field(min_length=1, max_length=200)
    cif: str | None = Field(default=None, max_length=20)
