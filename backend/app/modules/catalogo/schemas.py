import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrigenDato, TipoIVA, TipoProducto


class FamiliaBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=32)
    nombre: str = Field(min_length=1, max_length=160)
    parent_id: uuid.UUID | None = None
    orden: int = 0


class FamiliaCreate(FamiliaBase):
    pass


class FamiliaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, min_length=1, max_length=32)
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    parent_id: uuid.UUID | None = None
    orden: int | None = None


class FamiliaOut(FamiliaBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creado_por_nombre: str | None = None


class PrecioSuministroBase(BaseModel):
    proveedor_id: uuid.UUID
    precio: Decimal = Field(ge=0, decimal_places=4)
    moneda: str = Field(default="EUR", min_length=3, max_length=3)
    descuento: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    cantidad_minima: Decimal | None = Field(default=None, ge=0)
    plazo_entrega_dias: int | None = Field(default=None, ge=0)
    referencia_proveedor: str | None = Field(default=None, max_length=60)
    vigente_desde: date
    vigente_hasta: date | None = None
    es_preferente: bool = False
    notas: str | None = None


class PrecioSuministroCreate(PrecioSuministroBase):
    origen_dato: OrigenDato = OrigenDato.MANUAL


class PrecioSuministroUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proveedor_id: uuid.UUID | None = None
    precio: Decimal | None = Field(default=None, ge=0)
    moneda: str | None = Field(default=None, min_length=3, max_length=3)
    descuento: Decimal | None = Field(default=None, ge=0, le=100)
    cantidad_minima: Decimal | None = Field(default=None, ge=0)
    plazo_entrega_dias: int | None = Field(default=None, ge=0)
    referencia_proveedor: str | None = None
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    es_preferente: bool | None = None
    notas: str | None = None


class PrecioSuministroOut(PrecioSuministroBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    producto_id: uuid.UUID
    origen_dato: OrigenDato
    precio_neto: Decimal
    # Desnormalizado en la respuesta para no obligar al cliente a una segunda
    # llamada solo para pintar el nombre del proveedor en una tabla.
    proveedor_razon_social: str | None = None
    created_at: datetime
    updated_at: datetime


class ProductoBase(BaseModel):
    tipo: TipoProducto = TipoProducto.MATERIAL
    familia_id: uuid.UUID | None = None
    resumen: str = Field(min_length=1, max_length=250)
    descripcion: str | None = None
    unidad: str = Field(default="ud", min_length=1, max_length=10)
    tipo_iva: TipoIVA = TipoIVA.GENERAL
    precio_venta: Decimal | None = Field(default=None, ge=0)
    ean: str | None = Field(default=None, max_length=14)
    activo: bool = True


class ProductoCreate(ProductoBase):
    codigo: str | None = Field(default=None, max_length=32)
    origen_dato: OrigenDato = OrigenDato.MANUAL
    atributos: dict = Field(default_factory=dict)


class ProductoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoProducto | None = None
    familia_id: uuid.UUID | None = None
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    descripcion: str | None = None
    unidad: str | None = Field(default=None, min_length=1, max_length=10)
    tipo_iva: TipoIVA | None = None
    precio_venta: Decimal | None = Field(default=None, ge=0)
    ean: str | None = None
    activo: bool | None = None
    atributos: dict | None = None


class ProductoOut(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    origen_dato: OrigenDato
    atributos: dict
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class ProductoDetalle(ProductoOut):
    suministros: list[PrecioSuministroOut] = Field(default_factory=list)
