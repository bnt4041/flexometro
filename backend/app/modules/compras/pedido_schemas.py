import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.compras.models import EstadoPedido


class PedidoLineaBase(BaseModel):
    concepto_id: uuid.UUID | None = None
    descripcion: str | None = Field(default=None, max_length=250)
    unidad: str | None = Field(default=None, max_length=10)
    cantidad: Decimal = Field(gt=0)
    # Si no se indica y hay concepto, se toma el precio de referencia del
    # banco de precios (la tarifa preferente del proveedor) — mismo criterio
    # que `AlbaranLineaBase`.
    precio_unitario: Decimal | None = Field(default=None, ge=0)
    orden: int = 0


class PedidoLineaCreate(PedidoLineaBase):
    pass


class PedidoLineaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descripcion: str | None = None
    unidad: str | None = None
    cantidad: Decimal | None = Field(default=None, gt=0)
    precio_unitario: Decimal | None = Field(default=None, ge=0)
    orden: int | None = None


class PedidoLineaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pedido_id: uuid.UUID
    concepto_id: uuid.UUID | None
    descripcion: str
    unidad: str
    cantidad: Decimal
    precio_unitario: Decimal
    importe: Decimal
    orden: int


class PedidoBase(BaseModel):
    obra_id: uuid.UUID
    proveedor_id: uuid.UUID
    fecha: date
    fecha_entrega_prevista: date | None = None
    estado: EstadoPedido = EstadoPedido.PENDIENTE
    notas: str | None = None


class PedidoCreate(PedidoBase):
    codigo: str | None = Field(default=None, max_length=32)
    # De qué solicitud/oferta viene, si viene de ahí (vía "confirmar oferta
    # ganadora"). Si se dan `lineas` explícitas, mandan ellas siempre; si no
    # se dan y `origen_oferta_presupuesto_id` sí, se copian de las partidas
    # de esa oferta.
    origen_solicitud_id: uuid.UUID | None = None
    origen_oferta_presupuesto_id: uuid.UUID | None = None
    lineas: list[PedidoLineaCreate] = Field(default_factory=list)


class PedidoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date | None = None
    fecha_entrega_prevista: date | None = None
    estado: EstadoPedido | None = None
    notas: str | None = None


class PedidoOut(PedidoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    origen_solicitud_id: uuid.UUID | None
    origen_oferta_presupuesto_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class PedidoResumen(PedidoOut):
    proveedor_razon_social: str
    total: Decimal


class PedidoDetalle(PedidoOut):
    proveedor_razon_social: str
    lineas: list[PedidoLineaOut] = Field(default_factory=list)
    total: Decimal = Decimal("0.00")
