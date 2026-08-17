import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import OrigenDato, TipoPersona
from app.modules.terceros.models import EntidadContacto, FormaPago
from app.modules.terceros.nif import normalizar, validar_nif


def _normalizar_y_validar_nif(valor: str | None) -> str | None:
    if not valor:
        return None
    nif = normalizar(valor)
    if not validar_nif(nif):
        raise ValueError(f"'{valor}' no es un NIF/NIE/CIF válido")
    return nif


class ContactoBase(BaseModel):
    tratamiento: str | None = Field(default=None, max_length=32)
    nombre: str = Field(min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, max_length=160)
    cargo: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=30)
    movil: str | None = Field(default=None, max_length=30)
    es_principal: bool = False
    notas: str | None = None
    activo: bool = True


class ContactoCreate(ContactoBase):
    tercero_id: uuid.UUID | None = None


class ContactoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tratamiento: str | None = None
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = None
    cargo: str | None = None
    email: str | None = None
    telefono: str | None = None
    movil: str | None = None
    es_principal: bool | None = None
    notas: str | None = None
    activo: bool | None = None
    tercero_id: uuid.UUID | None = None


class ContactoOut(ContactoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tercero_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class TerceroBase(BaseModel):
    nif: str | None = Field(default=None, max_length=20)
    razon_social: str = Field(min_length=1, max_length=200)
    nombre_comercial: str | None = Field(default=None, max_length=200)
    tipo_persona: TipoPersona = TipoPersona.JURIDICA
    forma_juridica: str | None = Field(default=None, max_length=64)

    es_cliente: bool = False
    es_proveedor: bool = False
    es_subcontratista: bool = False

    email: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=30)
    web: str | None = Field(default=None, max_length=200)

    direccion: str | None = Field(default=None, max_length=250)
    codigo_postal: str | None = Field(default=None, max_length=10)
    ciudad: str | None = Field(default=None, max_length=120)
    provincia: str | None = Field(default=None, max_length=120)
    pais: str = Field(default="ES", min_length=2, max_length=2)

    iban: str | None = Field(default=None, max_length=34)
    forma_pago: FormaPago | None = None
    dias_pago: int | None = Field(default=None, ge=0, le=365)

    irpf_retencion: Decimal | None = Field(default=None, ge=0, le=100)
    inversion_sujeto_pasivo: bool = False
    rea_numero: str | None = Field(default=None, max_length=40)
    rea_caducidad: date | None = None

    notas: str | None = None
    activo: bool = True

    @field_validator("nif")
    @classmethod
    def _validar_nif(cls, valor: str | None) -> str | None:
        return _normalizar_y_validar_nif(valor)


class TerceroCreate(TerceroBase):
    # Si no se indica, se asigna el siguiente correlativo de la organización.
    codigo: str | None = Field(default=None, max_length=32)
    origen_dato: OrigenDato = OrigenDato.MANUAL
    contactos: list[ContactoBase] = Field(default_factory=list)


class TerceroUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nif: str | None = None
    razon_social: str | None = Field(default=None, min_length=1, max_length=200)
    nombre_comercial: str | None = None
    tipo_persona: TipoPersona | None = None
    forma_juridica: str | None = None
    es_cliente: bool | None = None
    es_proveedor: bool | None = None
    es_subcontratista: bool | None = None
    email: str | None = None
    telefono: str | None = None
    web: str | None = None
    direccion: str | None = None
    codigo_postal: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    pais: str | None = Field(default=None, min_length=2, max_length=2)
    iban: str | None = None
    forma_pago: FormaPago | None = None
    dias_pago: int | None = Field(default=None, ge=0, le=365)
    irpf_retencion: Decimal | None = Field(default=None, ge=0, le=100)
    inversion_sujeto_pasivo: bool | None = None
    rea_numero: str | None = None
    rea_caducidad: date | None = None
    notas: str | None = None
    activo: bool | None = None

    @field_validator("nif")
    @classmethod
    def _validar_nif(cls, valor: str | None) -> str | None:
        return _normalizar_y_validar_nif(valor)


class TerceroOut(TerceroBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    origen_dato: OrigenDato
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class TerceroDetalle(TerceroOut):
    contactos: list[ContactoOut] = Field(default_factory=list)


class ContactoAsociadoCreate(BaseModel):
    contacto_id: uuid.UUID
    rol: str | None = Field(default=None, max_length=80)


class ContactoAsociadoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entidad: EntidadContacto
    entidad_id: uuid.UUID
    contacto_id: uuid.UUID
    rol: str | None
    created_at: datetime
    # Desnormalizado en la respuesta para no obligar al cliente a una
    # segunda llamada solo para pintar el nombre en una lista.
    contacto_nombre: str
    contacto_apellidos: str | None = None
    contacto_cargo: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None
