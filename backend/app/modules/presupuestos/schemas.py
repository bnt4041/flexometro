import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrigenDato
from app.modules.presupuestos.models import (
    NaturalezaConcepto,
    OrigenPrecio,
    TipoConcepto,
)


class ConceptoBase(BaseModel):
    tipo: TipoConcepto
    naturaleza: NaturalezaConcepto = NaturalezaConcepto.SIN_CLASIFICAR
    unidad: str = Field(default="ud", min_length=1, max_length=10)
    resumen: str = Field(min_length=1, max_length=250)
    texto: str | None = None
    origen_precio: OrigenPrecio = OrigenPrecio.MANUAL
    producto_id: uuid.UUID | None = None
    costes_indirectos: Decimal | None = Field(default=None, ge=0, le=100)
    fecha_precio: date | None = None
    activo: bool = True


class ConceptoCreate(ConceptoBase):
    codigo: str | None = Field(default=None, max_length=32)
    # Solo se tiene en cuenta con origen_precio MANUAL; en los demás casos el
    # precio lo fija el cálculo.
    precio: Decimal = Field(default=Decimal("0.00"), ge=0)
    origen_dato: OrigenDato = OrigenDato.MANUAL


class ConceptoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoConcepto | None = None
    naturaleza: NaturalezaConcepto | None = None
    unidad: str | None = Field(default=None, min_length=1, max_length=10)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    precio: Decimal | None = Field(default=None, ge=0)
    origen_precio: OrigenPrecio | None = None
    producto_id: uuid.UUID | None = None
    costes_indirectos: Decimal | None = Field(default=None, ge=0, le=100)
    fecha_precio: date | None = None
    activo: bool | None = None


class ConceptoOut(ConceptoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    precio: Decimal
    origen_dato: OrigenDato
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class LineaOut(BaseModel):
    """Una línea del descompuesto, con los datos del hijo ya resueltos."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hijo_id: uuid.UUID
    hijo_codigo: str
    hijo_resumen: str
    hijo_unidad: str
    hijo_tipo: TipoConcepto
    hijo_precio: Decimal
    rendimiento: Decimal
    factor: Decimal
    orden: int
    # rendimiento x factor x precio, redondeado a dos como en el papel.
    importe: Decimal


class LineaCreate(BaseModel):
    hijo_id: uuid.UUID
    rendimiento: Decimal = Field(gt=0)
    factor: Decimal = Field(default=Decimal("1"), gt=0)
    orden: int = 0


class LineaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rendimiento: Decimal | None = Field(default=None, gt=0)
    factor: Decimal | None = Field(default=None, gt=0)
    orden: int | None = None


class ConceptoDetalle(ConceptoOut):
    lineas: list[LineaOut] = Field(default_factory=list)
    # Suma de las líneas, antes de aplicar costes indirectos.
    coste_directo: Decimal = Decimal("0.00")
    # simple / complejo / funcional, deducido de los hijos. No se almacena:
    # la clasificación se sigue de la estructura, no al revés.
    clase: str | None = None


class UsoOut(BaseModel):
    """Un concepto que contiene al consultado."""

    id: uuid.UUID
    codigo: str
    resumen: str
    tipo: TipoConcepto
    precio: Decimal
    rendimiento: Decimal


class NodoArbol(BaseModel):
    id: uuid.UUID
    codigo: str
    resumen: str
    unidad: str
    tipo: TipoConcepto
    precio: Decimal
    rendimiento: Decimal | None = None
    factor: Decimal | None = None
    importe: Decimal | None = None
    hijos: list["NodoArbol"] = Field(default_factory=list)


class ResultadoRecalculo(BaseModel):
    conceptos_modificados: int
    ids: list[uuid.UUID]
