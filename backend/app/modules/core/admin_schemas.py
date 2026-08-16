import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

_RE_SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class ModuloEstadoOut(BaseModel):
    code: str
    name: str
    depends_on: list[str]
    always_active: bool
    is_active: bool


class OrganizacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cuenta_id: uuid.UUID
    slug: str
    name: str
    cif: str | None
    is_active: bool
    created_at: datetime


class OrganizacionDetalle(OrganizacionOut):
    settings: dict
    modulos: list[ModuloEstadoOut] = Field(default_factory=list)


class OrganizacionCreate(BaseModel):
    # Mismo alfabeto que el atributo `organizacion` de Keycloak: minúsculas,
    # dígitos y guiones, sin empezar ni acabar en guion.
    slug: str = Field(min_length=2, max_length=64, pattern=_RE_SLUG)
    name: str = Field(min_length=1, max_length=200)
    cif: str | None = Field(default=None, max_length=20)


class OrganizacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    cif: str | None = None
    is_active: bool | None = None
