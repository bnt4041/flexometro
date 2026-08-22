import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    # El slug (mismo alfabeto que el atributo `organizacion` de Keycloak:
    # minúsculas, dígitos y guiones) ya no se teclea — se genera del nombre,
    # ver `service.crear_organizacion`.
    name: str = Field(min_length=1, max_length=200)
    cif: str | None = Field(default=None, max_length=20)


class OrganizacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    cif: str | None = None
    is_active: bool | None = None
