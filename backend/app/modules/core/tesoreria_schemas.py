import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.core.tesoreria_models import TipoCuentaFinanciera


class CuentaFinancieraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo: TipoCuentaFinanciera
    banco: str | None
    iban: str | None
    bic: str | None
    es_predeterminada: bool
    activa: bool
    notas: str | None


class CuentaFinancieraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    tipo: TipoCuentaFinanciera
    banco: str | None = Field(default=None, max_length=120)
    iban: str | None = Field(default=None, max_length=34)
    bic: str | None = Field(default=None, max_length=11)
    es_predeterminada: bool = False
    activa: bool = True
    notas: str | None = None

    @model_validator(mode="after")
    def _caja_sin_datos_de_banco(self) -> "CuentaFinancieraCreate":
        if self.tipo == TipoCuentaFinanciera.CAJA and (self.banco or self.iban or self.bic):
            raise ValueError("Una caja de efectivo no lleva banco, IBAN ni BIC")
        return self


class CuentaFinancieraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    tipo: TipoCuentaFinanciera | None = None
    banco: str | None = Field(default=None, max_length=120)
    iban: str | None = Field(default=None, max_length=34)
    bic: str | None = Field(default=None, max_length=11)
    es_predeterminada: bool | None = None
    activa: bool | None = None
    notas: str | None = None
