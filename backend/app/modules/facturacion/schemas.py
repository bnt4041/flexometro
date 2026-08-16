import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import TipoIVA
from app.modules.facturacion.models import EstadoCertificacion, EstadoFactura
from app.modules.terceros.models import FormaPago


# --- Certificación ---


class LineaCertificarIn(BaseModel):
    """Lo que pide el cliente para certificar una partida: solo cuánto lleva
    ejecutado en total. El resto (anterior, periodo, importe) lo resuelve el
    servidor."""

    partida_id: uuid.UUID
    medicion_actual: Decimal = Field(ge=0)


class CertificacionCreate(BaseModel):
    obra_id: uuid.UUID
    fecha: date
    retencion_garantia_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    notas: str | None = None
    lineas: list[LineaCertificarIn] = Field(default_factory=list)


class CertificacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date | None = None
    retencion_garantia_pct: Decimal | None = Field(default=None, ge=0, le=100)
    notas: str | None = None


class CertificacionLineaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID
    codigo: str
    resumen: str
    unidad: str
    precio: Decimal
    medicion_anterior: Decimal
    medicion_actual: Decimal
    medicion_periodo: Decimal
    importe_periodo: Decimal
    orden: int


class CertificacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    numero: int
    obra_id: uuid.UUID
    fecha: date
    estado: EstadoCertificacion
    retencion_garantia_pct: Decimal
    notas: str | None
    creado_por_nombre: str | None = None


class CertificacionDetalle(CertificacionOut):
    lineas: list[CertificacionLineaOut] = Field(default_factory=list)
    importe_ejecutado: Decimal
    importe_retenido: Decimal
    importe_liquido: Decimal
    facturada: bool


# --- Factura ---


class FacturaSuelta(BaseModel):
    """Factura sin certificación: un anticipo, una revisión de precios..."""

    obra_id: uuid.UUID
    cliente_id: uuid.UUID | None = None
    concepto: str = Field(min_length=1, max_length=250)
    base_imponible: Decimal = Field(ge=0)
    tipo_iva: TipoIVA = TipoIVA.GENERAL
    inversion_sujeto_pasivo: bool = False
    serie: str | None = Field(default=None, max_length=10)
    fecha_vencimiento: date | None = None
    notas: str | None = None


class GenerarDesdeCertificacion(BaseModel):
    concepto: str | None = None
    serie: str | None = Field(default=None, max_length=10)
    fecha_vencimiento: date | None = None
    notas: str | None = None


class FacturaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concepto: str | None = None
    fecha_vencimiento: date | None = None
    notas: str | None = None


class FacturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    serie: str
    numero: int | None
    obra_id: uuid.UUID
    certificacion_id: uuid.UUID | None
    cliente_id: uuid.UUID
    concepto: str
    fecha_emision: date | None
    fecha_vencimiento: date | None
    base_imponible: Decimal
    tipo_iva: TipoIVA
    inversion_sujeto_pasivo: bool
    cuota_iva: Decimal
    total: Decimal
    estado: EstadoFactura
    motivo_anulacion: str | None
    notificado_n8n_en: datetime | None
    notas: str | None
    creado_por_nombre: str | None = None


class FacturaResumen(FacturaOut):
    cliente_razon_social: str
    cobrado: Decimal
    pendiente: Decimal
    situacion_cobro: str  # pendiente / parcial / cobrada
    vencida: bool


class CobroCreate(BaseModel):
    fecha: date
    importe: Decimal = Field(gt=0)
    forma_pago: FormaPago | None = None
    notas: str | None = None


class CobroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_id: uuid.UUID
    fecha: date
    importe: Decimal
    forma_pago: FormaPago | None
    notas: str | None


class FacturaDetalle(FacturaResumen):
    cobros: list[CobroOut] = Field(default_factory=list)


class AnularFactura(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)
