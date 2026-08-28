import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.compras.models import EstadoPedido, TipoPedido


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
    tipo: TipoPedido = TipoPedido.PROVEEDOR
    obra_id: uuid.UUID
    proveedor_id: uuid.UUID | None = None
    cliente_id: uuid.UUID | None = None
    fecha: date
    fecha_entrega_prevista: date | None = None
    estado: EstadoPedido = EstadoPedido.PENDIENTE
    notas: str | None = None

    @model_validator(mode="after")
    def _tercero_segun_tipo(self) -> "PedidoBase":
        if self.tipo == TipoPedido.CLIENTE:
            if self.cliente_id is None or self.proveedor_id is not None:
                raise ValueError(
                    "Un pedido de cliente necesita cliente_id, y no proveedor_id"
                )
        else:
            if self.proveedor_id is None or self.cliente_id is not None:
                raise ValueError(
                    "Un pedido a proveedor necesita proveedor_id, y no cliente_id"
                )
        return self


class PedidoCreate(PedidoBase):
    codigo: str | None = Field(default=None, max_length=32)
    # De qué solicitud/oferta viene, si viene de ahí (vía "confirmar oferta
    # ganadora") — solo aplica a `tipo=proveedor`. Si se dan `lineas`
    # explícitas, mandan ellas siempre; si no se dan y
    # `origen_oferta_presupuesto_id` sí, se copian de las partidas de esa
    # oferta (o del presupuesto de cliente, en un pedido de cliente).
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
    # El cliente o el proveedor, según `tipo`.
    tercero_razon_social: str
    total: Decimal


class PedidoDetalle(PedidoOut):
    tercero_razon_social: str
    lineas: list[PedidoLineaOut] = Field(default_factory=list)
    total: Decimal = Decimal("0.00")
