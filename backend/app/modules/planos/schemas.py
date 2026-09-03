import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.planos.enums import OrigenPlano, TipoElemento


class Punto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: Decimal
    y: Decimal


class HojaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: int
    nombre: str | None = None
    ancho: Decimal
    alto: Decimal
    metros_por_unidad: Decimal | None = None
    calibracion: dict | None = None
    dibujo: dict | None = None


class CapaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    color: str
    visible: bool
    bloqueada: bool
    orden: int


class CapaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    color: str = Field(default="#b45309", pattern=r"^#[0-9a-fA-F]{6}$")
    visible: bool = True
    bloqueada: bool = False
    orden: int = 0


class OrdenCapasIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Las capas del plano en el orden en que se quieren, de abajo arriba: la
    #: última se pinta encima de todas.
    capa_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class ElementoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hoja_id: uuid.UUID
    capa_id: uuid.UUID | None = None
    tipo: TipoElemento
    geometria: list
    texto: str | None = None
    color: str | None = None
    valor: Decimal | None = None
    unidad: str | None = None
    linea_medicion_id: uuid.UUID | None = None
    #: Lo dibujó la IA mirando la imagen: su geometría es aproximada hasta que
    #: alguien la revisa, y por eso se enseña marcado.
    propuesto_ia: bool = False
    creado_por_nombre: str | None = None
    created_at: datetime


class ElementoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoElemento
    #: Tope generoso pero no infinito: una polilínea de cien mil puntos es un
    #: error de la interfaz, no un replanteo.
    geometria: list[Punto] = Field(min_length=1, max_length=5000)
    capa_id: uuid.UUID | None = None
    texto: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class PlanoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    obra_id: uuid.UUID | None = None
    presupuesto_id: uuid.UUID | None = None
    origen: OrigenPlano
    nombre_archivo: str
    content_type: str
    tamano_bytes: int
    creado_por_nombre: str | None = None
    created_at: datetime


class PlanoDetalle(PlanoOut):
    hojas: list[HojaOut] = []
    capas: list[CapaOut] = []


class PlanoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    obra_id: uuid.UUID | None = None
    presupuesto_id: uuid.UUID | None = None


class CalibracionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: Punto
    b: Punto
    #: Lo que mide de verdad entre esos dos puntos. En metros.
    distancia_m: Decimal = Field(gt=0)


class AplicarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partida_id: uuid.UUID


class AplicadaOut(BaseModel):
    linea_medicion_id: uuid.UUID
    valor: Decimal
    unidad: str


class CotaLeidaOut(BaseModel):
    texto: str
    metros: Decimal
    donde: str | None = None


class LecturaIaOut(BaseModel):
    """Lo que la IA ha leído del plano. Nada de esto se ha aplicado: son
    propuestas para que alguien decida."""

    #: Denominador de la escala impresa (50 para «1:50»). Si viene, se puede
    #: calibrar exacto y sin pinchar nada.
    escala_impresa: int | None = None
    escala_texto: str | None = None
    #: `True` si esa escala se puede aplicar a esta hoja. En una imagen no,
    #: porque un píxel no mide nada sin conocer la resolución del escaneo.
    escala_aplicable: bool = False
    cotas: list[CotaLeidaOut] = []
    resumen: str | None = None
    avisos: list[str] = []


class RevisionIaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Lo que se le pide en concreto («cuenta las puertas», «mide el salón»).
    #: Sin esto hace una revisión general del plano.
    peticion: str | None = Field(default=None, max_length=500)
    #: `False` para que solo lea y responda, sin dibujar nada encima.
    dibujar: bool = True


class RevisionIaOut(LecturaIaOut):
    """Lo que ha hecho la IA al revisar la hoja.

    A diferencia de `LecturaIaOut`, esto SÍ ha escrito: puede haber calibrado
    la hoja (si el plano llevaba su escala escrita, que es exacta) y puede
    haber dejado elementos dibujados, siempre marcados como propuesta.
    """

    #: Lo que responde a lo que se le haya pedido.
    respuesta: str | None = None
    #: Cuántos elementos ha dejado dibujados, ya marcados como propuesta.
    elementos_creados: int = 0
    #: `True` si ha calibrado la hoja con la escala impresa que ha leído.
    calibrada: bool = False


class EscalaImpresaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: 50 para «1:50».
    denominador: int = Field(gt=0, le=10000)
