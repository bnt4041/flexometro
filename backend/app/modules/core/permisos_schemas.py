import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Alcance


class ModuloDisponibleOut(BaseModel):
    code: str
    name: str


class GrupoPermisoIn(BaseModel):
    module_code: str
    ver: Alcance = Alcance.NINGUNO
    editar: Alcance = Alcance.NINGUNO
    #: En `crear` el alcance no significa nada: lo que creas es tuyo. Solo
    #: cuenta si es NINGUNO o no.
    crear: Alcance = Alcance.NINGUNO
    borrar: Alcance = Alcance.NINGUNO


class GrupoPermisoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_code: str
    ver: Alcance
    editar: Alcance
    crear: Alcance
    borrar: Alcance


class GrupoMiembroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    usuario_subject: str
    usuario_nombre: str


class GrupoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=250)


class GrupoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    descripcion: str | None = None


class GrupoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    nombre: str
    descripcion: str | None
    created_at: datetime


class GrupoDetalle(GrupoOut):
    permisos: list[GrupoPermisoOut] = Field(default_factory=list)
    miembros: list[GrupoMiembroOut] = Field(default_factory=list)


class EstablecerPermisosIn(BaseModel):
    permisos: list[GrupoPermisoIn] = Field(default_factory=list)


class AnadirMiembroIn(BaseModel):
    usuario_subject: str = Field(min_length=1, max_length=120)
    usuario_nombre: str = Field(min_length=1, max_length=200)


class UsuarioKeycloakOut(BaseModel):
    id: str
    username: str
    email: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    enabled: bool = True
    roles: list[str] = Field(default_factory=list)


class ActualizarUsuarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    nombre: str | None = None
    apellidos: str | None = None
    habilitado: bool | None = None
