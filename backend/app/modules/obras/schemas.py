import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.obras.models import EstadoObra


class PersonalBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, max_length=160)
    categoria: str | None = Field(default=None, max_length=60)
    coste_hora: Decimal = Field(default=Decimal("0.00"), ge=0)
    activo: bool = True
    notas: str | None = None


class PersonalCreate(PersonalBase):
    codigo: str | None = Field(default=None, max_length=32)


class PersonalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = None
    categoria: str | None = None
    coste_hora: Decimal | None = Field(default=None, ge=0)
    activo: bool | None = None
    notas: str | None = None


class PersonalOut(PersonalBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class ParteTrabajoBase(BaseModel):
    fecha: date
    horas: Decimal = Field(gt=0, le=24)
    capitulo_id: uuid.UUID | None = None
    notas: str | None = None


class ParteTrabajoCreate(ParteTrabajoBase):
    pass


class ParteTrabajoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date | None = None
    horas: Decimal | None = Field(default=None, gt=0, le=24)
    capitulo_id: uuid.UUID | None = None
    notas: str | None = None


class ParteTrabajoOut(ParteTrabajoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asignacion_id: uuid.UUID
    coste: Decimal


class AsignacionCreate(BaseModel):
    personal_id: uuid.UUID
    fecha_desde: date
    fecha_hasta: date | None = None
    # Si no se indica, se copia el coste/hora actual de Personal.
    coste_hora: Decimal | None = Field(default=None, ge=0)
    notas: str | None = None


class AsignacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    coste_hora: Decimal | None = Field(default=None, ge=0)
    notas: str | None = None


class AsignacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    obra_id: uuid.UUID
    personal_id: uuid.UUID
    coste_hora: Decimal
    fecha_desde: date
    fecha_hasta: date | None
    notas: str | None


class AsignacionDetalle(AsignacionOut):
    personal_nombre: str
    personal_categoria: str | None
    partes: list[ParteTrabajoOut] = Field(default_factory=list)
    horas_totales: Decimal = Decimal("0.00")
    coste_total: Decimal = Decimal("0.00")


class ObraBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=250)
    jefe_obra_id: uuid.UUID | None = None
    estado: EstadoObra = EstadoObra.PLANIFICADA
    fecha_inicio: date | None = None
    fecha_fin_prevista: date | None = None
    fecha_fin_real: date | None = None
    notas: str | None = None


class ObraCreate(ObraBase):
    codigo: str | None = Field(default=None, max_length=32)
    presupuesto_id: uuid.UUID


class ObraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=250)
    jefe_obra_id: uuid.UUID | None = None
    estado: EstadoObra | None = None
    fecha_inicio: date | None = None
    fecha_fin_prevista: date | None = None
    fecha_fin_real: date | None = None
    notas: str | None = None


class ObraOut(ObraBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    presupuesto_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class ObraResumen(ObraOut):
    presupuesto_codigo: str
    presupuesto_nombre: str
    pem: Decimal


class ObraDetalle(ObraOut):
    presupuesto_codigo: str
    presupuesto_nombre: str
    asignaciones: list[AsignacionOut] = Field(default_factory=list)
