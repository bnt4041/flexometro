import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.automatizaciones.enums import EstadoEjecucion, EstadoPaso


class CampoNodoOut(BaseModel):
    nombre: str
    etiqueta: str
    tipo: str
    opciones: list[tuple[str, str]] = []
    ayuda: str = ""
    obligatorio: bool = True
    por_defecto: object = None
    admite_expresiones: bool = True


class TipoNodoOut(BaseModel):
    tipo: str
    categoria: str
    etiqueta: str
    descripcion: str
    icono: str
    campos: list[CampoNodoOut] = []
    salidas: list[tuple[str, str]] = []


class AutomatizacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: str | None = None
    activa: bool
    definicion: dict
    evento_disparador: str | None = None
    created_at: datetime
    #: Problemas del flujo, en lenguaje llano. Se enseñan sin impedir guardar.
    problemas: list[str] = []
    #: Solo al crear un disparador de webhook, y solo esa vez.
    token: str | None = None
    #: La URL a la que tiene que llamar el otro sistema, ya montada.
    url_webhook: str | None = None


class AutomatizacionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=160)
    descripcion: str | None = None
    activa: bool = False
    definicion: dict = Field(default_factory=dict)


class PasoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nodo_id: str
    tipo_nodo: str
    orden: int
    estado: EstadoPaso
    salida: dict
    ruta: str | None = None
    error: str | None = None
    duracion_ms: int | None = None


class EjecucionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estado: EstadoEjecucion
    disparador: str
    entrada: dict
    error: str | None = None
    terminada_en: datetime | None = None
    created_at: datetime
    pasos: list[PasoOut] = []
