import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.core.billing_models import MotivoDescuento, TipoDescuento


class TarifaModuloIn(BaseModel):
    module_code: str = Field(min_length=1, max_length=64)
    precio_mensual: Decimal = Field(ge=0)


class TarifaModuloOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_code: str
    precio_mensual: Decimal


class TarifaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str | None = None
    precio_1000_tokens_deepseek: Decimal = Field(default=Decimal("0.0000"), ge=0)
    precio_1000_tokens_gemini: Decimal = Field(default=Decimal("0.0000"), ge=0)
    # Créditos IA (Fase 38): ver `app/modules/core/creditos_service.py`.
    valor_credito_euros: Decimal = Field(default=Decimal("0.001000"), ge=0)
    creditos_ia_incluidos_mes: int = Field(default=0, ge=0)
    modulos: list[TarifaModuloIn] = Field(default_factory=list)


class TarifaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    descripcion: str | None = None
    activa: bool | None = None
    precio_1000_tokens_deepseek: Decimal | None = Field(default=None, ge=0)
    precio_1000_tokens_gemini: Decimal | None = Field(default=None, ge=0)
    valor_credito_euros: Decimal | None = Field(default=None, ge=0)
    creditos_ia_incluidos_mes: int | None = Field(default=None, ge=0)
    # Si viene, sustituye la lista entera de precios por módulo.
    modulos: list[TarifaModuloIn] | None = None


class TarifaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: str | None
    activa: bool
    precio_1000_tokens_deepseek: Decimal
    precio_1000_tokens_gemini: Decimal
    valor_credito_euros: Decimal
    creditos_ia_incluidos_mes: int
    created_at: datetime


class TarifaDetalle(TarifaOut):
    modulos: list[TarifaModuloOut] = Field(default_factory=list)


class DescuentoCreate(BaseModel):
    # Agrupación opcional bajo una tarifa, solo para listar/buscar — no limita
    # a qué organizaciones se le puede aplicar después.
    tarifa_id: uuid.UUID | None = None
    nombre: str = Field(min_length=1, max_length=120)
    motivo: MotivoDescuento = MotivoDescuento.OTRO
    tipo: TipoDescuento
    valor: Decimal = Field(gt=0)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class DescuentoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    motivo: MotivoDescuento | None = None
    valor: Decimal | None = Field(default=None, gt=0)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    activo: bool | None = None


class DescuentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tarifa_id: uuid.UUID | None
    nombre: str
    motivo: MotivoDescuento
    tipo: TipoDescuento
    valor: Decimal
    vigente_desde: date | None
    vigente_hasta: date | None
    activo: bool


class AplicarDescuentosIn(BaseModel):
    descuento_ids: list[uuid.UUID] = Field(min_length=1)


class AplicacionDescuentoOut(BaseModel):
    id: uuid.UUID
    cuenta_id: uuid.UUID
    descuento: DescuentoOut
    aplicado_en: datetime
    anulado_en: datetime | None
    vigente: bool


class CosteEstimadoOut(BaseModel):
    tarifa_nombre: str | None
    subtotal_modulos: Decimal
    subtotal_ia: Decimal
    subtotal: Decimal
    descuentos_aplicados: Decimal
    total: Decimal
    tokens_deepseek_mes: int
    tokens_gemini_mes: int
