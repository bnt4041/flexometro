import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.contratos.models import EstadoContrato, TipoContrato


class ContratoBase(BaseModel):
    tipo: TipoContrato
    obra_id: uuid.UUID
    cliente_id: uuid.UUID | None = None
    proveedor_id: uuid.UUID | None = None
    # El presupuesto que formaliza, si lo hay — el principal de la obra para
    # uno de cliente, normalmente, o la oferta aceptada para uno de proveedor.
    presupuesto_id: uuid.UUID | None = None
    fecha_firma: date | None = None
    fecha_inicio: date | None = None
    fecha_fin_prevista: date | None = None
    estado: EstadoContrato = EstadoContrato.BORRADOR
    importe: Decimal | None = Field(default=None, ge=0)
    retencion_garantia_pct: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    notas: str | None = None

    @model_validator(mode="after")
    def _tercero_segun_tipo(self) -> "ContratoBase":
        if self.tipo == TipoContrato.CLIENTE:
            if self.cliente_id is None or self.proveedor_id is not None:
                raise ValueError(
                    "Un contrato de cliente necesita cliente_id, y no proveedor_id"
                )
        else:
            if self.proveedor_id is None or self.cliente_id is not None:
                raise ValueError(
                    "Un contrato de proveedor necesita proveedor_id, y no cliente_id"
                )
        return self


class ContratoCreate(ContratoBase):
    codigo: str | None = Field(default=None, max_length=32)


class ContratoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presupuesto_id: uuid.UUID | None = None
    fecha_firma: date | None = None
    fecha_inicio: date | None = None
    fecha_fin_prevista: date | None = None
    estado: EstadoContrato | None = None
    importe: Decimal | None = Field(default=None, ge=0)
    retencion_garantia_pct: Decimal | None = Field(default=None, ge=0, le=100)
    notas: str | None = None


class ContratoOut(ContratoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class ContratoResumen(ContratoOut):
    # El cliente o el proveedor, según `tipo` — resuelto en el router.
    tercero_razon_social: str
