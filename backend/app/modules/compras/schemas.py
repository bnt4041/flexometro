import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import TipoIVA
from app.modules.compras.models import EstadoAlbaran, EstadoFacturaRecibida, TipoAlbaran


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
    tipo: TipoAlbaran = TipoAlbaran.PROVEEDOR
    obra_id: uuid.UUID
    proveedor_id: uuid.UUID | None = None
    cliente_id: uuid.UUID | None = None
    numero_proveedor: str | None = Field(default=None, max_length=60)
    fecha: date
    estado: EstadoAlbaran = EstadoAlbaran.BORRADOR
    notas: str | None = None
    # De qué pedido viene esta entrega — opcional, se puede seguir dando de
    # alta un albarán directo, sin pedido de por medio.
    pedido_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _tercero_segun_tipo(self) -> "AlbaranBase":
        if self.tipo == TipoAlbaran.CLIENTE:
            if self.cliente_id is None or self.proveedor_id is not None:
                raise ValueError(
                    "Un albarán de cliente necesita cliente_id, y no proveedor_id"
                )
        else:
            if self.proveedor_id is None or self.cliente_id is not None:
                raise ValueError(
                    "Un albarán de proveedor necesita proveedor_id, y no cliente_id"
                )
        return self


class AlbaranCreate(AlbaranBase):
    codigo: str | None = Field(default=None, max_length=32)
    lineas: list[AlbaranLineaCreate] = Field(default_factory=list)


class AlbaranUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_proveedor: str | None = None
    fecha: date | None = None
    estado: EstadoAlbaran | None = None
    notas: str | None = None
    pedido_id: uuid.UUID | None = None


class AlbaranOut(AlbaranBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class AlbaranResumen(AlbaranOut):
    tercero_razon_social: str
    total: Decimal


class AlbaranDetalle(AlbaranOut):
    tercero_razon_social: str
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


# --- Facturas de proveedor ---
#
# No las emitimos nosotros: no llevan serie ni numeración legal. Lo que las
# identifica frente al proveedor es SU número.


class FacturaRecibidaBase(BaseModel):
    numero_proveedor: str = Field(min_length=1, max_length=60)
    fecha: date
    fecha_vencimiento: date | None = None
    base_imponible: Decimal = Field(ge=0)
    tipo_iva: TipoIVA = TipoIVA.GENERAL
    inversion_sujeto_pasivo: bool = False
    notas: str | None = None


class FacturaRecibidaCreate(FacturaRecibidaBase):
    obra_id: uuid.UUID
    proveedor_id: uuid.UUID
    # Si vienen, mandan sobre lo calculado: es lo que dice el papel, y un
    # céntimo de diferencia por el redondeo del proveedor no puede impedir
    # registrar su factura.
    cuota_iva: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, ge=0)
    albaran_ids: list[uuid.UUID] = Field(default_factory=list)


class FacturaRecibidaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_proveedor: str | None = Field(default=None, min_length=1, max_length=60)
    fecha: date | None = None
    fecha_vencimiento: date | None = None
    base_imponible: Decimal | None = Field(default=None, ge=0)
    tipo_iva: TipoIVA | None = None
    inversion_sujeto_pasivo: bool | None = None
    cuota_iva: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, ge=0)
    estado: EstadoFacturaRecibida | None = None
    fecha_pago: date | None = None
    notas: str | None = None
    # A None se dejan como están; una lista (incluso vacía) los reemplaza.
    albaran_ids: list[uuid.UUID] | None = None


class FacturaRecibidaOut(FacturaRecibidaBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    obra_id: uuid.UUID
    proveedor_id: uuid.UUID
    cuota_iva: Decimal
    total: Decimal
    estado: EstadoFacturaRecibida
    fecha_pago: date | None
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None
    # Resueltos en el router: el listado los enseña sin pedirlos uno a uno.
    proveedor_razon_social: str = ""
    albaran_ids: list[uuid.UUID] = Field(default_factory=list)
    albaran_codigos: list[str] = Field(default_factory=list)


class TotalesComprasObra(BaseModel):
    """Lo comprado en la obra, para cuadrar entregas con facturas."""

    albaranes_total: Decimal
    facturas_base: Decimal
    facturas_total: Decimal
    pendiente_de_pago: Decimal
    # Albaranes que no aparecen en ninguna factura: material entregado que
    # nadie ha facturado todavía.
    albaranes_sin_facturar: int
