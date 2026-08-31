import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.eventos import Disparador


class ParametroOut(BaseModel):
    nombre: str
    etiqueta: str
    por_defecto: int
    minimo: int
    maximo: int
    sufijo: str


class TipoEventoOut(BaseModel):
    codigo: str
    modulo: str
    etiqueta: str
    descripcion: str
    disparador: Disparador
    parametros: list[ParametroOut] = []


class SuscripcionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo_evento: str
    usuario_subject: str | None = None
    grupo_id: uuid.UUID | None = None
    canales: list[str]
    parametros: dict
    activa: bool


class SuscripcionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_evento: str = Field(min_length=1, max_length=64)
    usuario_subject: str | None = None
    grupo_id: uuid.UUID | None = None
    #: Vacío = borrar la suscripción. Una que no avisa por ningún sitio es lo
    #: mismo que no estar suscrito.
    canales: list[str] = Field(default_factory=list)
    parametros: dict = Field(default_factory=dict)
    activa: bool = True

    @model_validator(mode="after")
    def _uno_u_otro(self) -> "SuscripcionIn":
        if bool(self.usuario_subject) == bool(self.grupo_id):
            raise ValueError("Es de una persona o de un grupo, no de las dos cosas")
        return self


class PreferenciaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telefono: str | None = Field(default=None, max_length=30)
    silenciado: bool = False


class PreferenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    telefono: str | None = None
    silenciado: bool = False
