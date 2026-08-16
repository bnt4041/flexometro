import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.compras.models import EstadoAlbaran


class AlbaranLineaBase(BaseModel):
    concepto_id: uuid.UUID | None = None
    capitulo_id: uuid.UUID | None = None
    descripcion: str | None = Field(default=None, max_length=250)
    unidad: str | None = Field(default=None, max_length=10)
    cantidad: Decimal = Field(gt=0)
    # Si no se indica y hay concepto, se toma el precio de referencia del
    # banco de precios (la tarifa preferente del proveedor).
    precio_unitario: Decimal | None = Field(default=None, ge=0)
    orden: int = 0


class AlbaranLineaCreate(AlbaranLineaBase):
    pass


class AlbaranLineaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descripcion: str | None = None
    unidad: str | None = None
    cantidad: Decimal | None = Field(default=None, gt=0)
    precio_unitario: Decimal | None = Field(default=None, ge=0)
    capitulo_id: uuid.UUID | None = None
    orden: int | None = None


class AlbaranLineaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    albaran_id: uuid.UUID
    concepto_id: uuid.UUID | None
    capitulo_id: uuid.UUID | None
    descripcion: str
    unidad: str
    cantidad: Decimal
    precio_unitario: Decimal
    importe: Decimal
    orden: int


class AlbaranBase(BaseModel):
    obra_id: uuid.UUID
    proveedor_id: uuid.UUID
    numero_proveedor: str | None = Field(default=None, max_length=60)
    fecha: date
    estado: EstadoAlbaran = EstadoAlbaran.BORRADOR
    notas: str | None = None


class AlbaranCreate(AlbaranBase):
    codigo: str | None = Field(default=None, max_length=32)
    lineas: list[AlbaranLineaCreate] = Field(default_factory=list)


class AlbaranUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_proveedor: str | None = None
    fecha: date | None = None
    estado: EstadoAlbaran | None = None
    notas: str | None = None


class AlbaranOut(AlbaranBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class AlbaranResumen(AlbaranOut):
    proveedor_razon_social: str
    total: Decimal


class AlbaranDetalle(AlbaranOut):
    proveedor_razon_social: str
    lineas: list[AlbaranLineaOut] = Field(default_factory=list)
    total: Decimal = Decimal("0.00")


# --- Informe de coste real vs. presupuestado ---


class CosteCapitulo(BaseModel):
    capitulo_id: uuid.UUID | None
    codigo: str
    resumen: str
    presupuestado: Decimal
    real_materiales: Decimal
    real_mano_obra: Decimal
    real_total: Decimal
    desviacion: Decimal
    desviacion_pct: Decimal | None


class InformeCosteObra(BaseModel):
    obra_id: uuid.UUID
    obra_codigo: str
    obra_nombre: str
    capitulos: list[CosteCapitulo]
    totales: CosteCapitulo
