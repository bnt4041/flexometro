import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrigenDato, TipoIVA
from app.modules.presupuestos.models_presupuesto import EstadoPresupuesto


class LineaMedicionBase(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int = 0


class LineaMedicionCreate(LineaMedicionBase):
    pass


class LineaMedicionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comentario: str | None = None
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int | None = None


class LineaMedicionOut(LineaMedicionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID
    parcial: Decimal


class PartidaCreate(BaseModel):
    # Con concepto_id se copian código, resumen, unidad y precio del cuadro.
    # Sin él es una partida alzada y hay que dar los datos a mano.
    concepto_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    orden: int = 0
    lineas: list[LineaMedicionCreate] = Field(default_factory=list)


class PartidaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    orden: int | None = None
    capitulo_id: uuid.UUID | None = None


class PartidaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    capitulo_id: uuid.UUID
    concepto_id: uuid.UUID | None
    codigo: str
    resumen: str
    texto: str | None
    unidad: str
    precio: Decimal
    medicion: Decimal
    importe: Decimal
    orden: int


class PartidaDetalle(PartidaOut):
    lineas: list[LineaMedicionOut] = Field(default_factory=list)
    # Precio actual del concepto en el cuadro, si difiere del de la partida.
    precio_cuadro: Decimal | None = None


class CapituloCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str = Field(min_length=1, max_length=250)
    texto: str | None = None
    orden: int = 0


class CapituloUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    orden: int | None = None


class NodoCapitulo(BaseModel):
    id: uuid.UUID
    codigo: str
    resumen: str
    texto: str | None = None
    orden: int
    importe: Decimal
    partidas: list[PartidaOut] = Field(default_factory=list)
    hijos: list["NodoCapitulo"] = Field(default_factory=list)


class TotalesOut(BaseModel):
    pem: Decimal
    gastos_generales: Decimal
    beneficio_industrial: Decimal
    pec_sin_iva: Decimal
    porcentaje_iva: Decimal
    iva: Decimal
    total: Decimal


class PresupuestoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=250)
    descripcion: str | None = None
    cliente_id: uuid.UUID | None = None
    emplazamiento: str | None = Field(default=None, max_length=250)
    fecha: date | None = None
    validez_dias: int | None = Field(default=None, ge=0)
    gastos_generales: Decimal = Field(default=Decimal("13.00"), ge=0, le=100)
    beneficio_industrial: Decimal = Field(default=Decimal("6.00"), ge=0, le=100)
    tipo_iva: TipoIVA = TipoIVA.GENERAL
    inversion_sujeto_pasivo: bool = False
    tipo_obra: str | None = Field(default=None, max_length=120)
    notas: str | None = None


class PresupuestoCreate(PresupuestoBase):
    codigo: str | None = Field(default=None, max_length=32)
    origen_dato: OrigenDato = OrigenDato.MANUAL


class PresupuestoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=250)
    descripcion: str | None = None
    cliente_id: uuid.UUID | None = None
    emplazamiento: str | None = None
    fecha: date | None = None
    validez_dias: int | None = Field(default=None, ge=0)
    estado: EstadoPresupuesto | None = None
    gastos_generales: Decimal | None = Field(default=None, ge=0, le=100)
    beneficio_industrial: Decimal | None = Field(default=None, ge=0, le=100)
    tipo_iva: TipoIVA | None = None
    inversion_sujeto_pasivo: bool | None = None
    precios_bloqueados: bool | None = None
    notas: str | None = None


class PresupuestoOut(PresupuestoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    estado: EstadoPresupuesto
    precios_bloqueados: bool
    raiz_id: uuid.UUID | None
    version: int
    es_plantilla: bool
    origen_dato: OrigenDato
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class PresupuestoResumen(PresupuestoOut):
    """Fila de listado: lleva el total calculado, sin el árbol."""

    total: Decimal
    pem: Decimal


class PresupuestoDetalle(PresupuestoOut):
    capitulos: list[NodoCapitulo] = Field(default_factory=list)
    totales: TotalesOut
    # Cuántas partidas tienen un precio distinto del que hay ahora en el
    # cuadro. Solo puede pasar con los precios bloqueados.
    partidas_desactualizadas: int = 0


class ResultadoSincronizacion(BaseModel):
    partidas_actualizadas: int


# --- Versiones y plantillas ---


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nombre: str
    version: int
    estado: EstadoPresupuesto
    fecha: date | None
    created_at: datetime


class GuardarComoPlantilla(BaseModel):
    nombre: str = Field(min_length=1, max_length=250)
    codigo: str | None = Field(default=None, max_length=32)
    tipo_obra: str | None = Field(default=None, max_length=120)
    # Lo reutilizable de un presupuesto es qué partidas lleva, no cuántos
    # metros medía aquella obra concreta.
    con_mediciones: bool = False


class InstanciarPlantilla(BaseModel):
    nombre: str = Field(min_length=1, max_length=250)
    codigo: str | None = Field(default=None, max_length=32)
    cliente_id: uuid.UUID | None = None
    emplazamiento: str | None = Field(default=None, max_length=250)


class CambioOut(BaseModel):
    codigo: str
    resumen: str
    unidad: str
    medicion_a: Decimal | None = None
    medicion_b: Decimal | None = None
    precio_a: Decimal | None = None
    precio_b: Decimal | None = None
    importe_a: Decimal
    importe_b: Decimal
    delta: Decimal


class ComparacionOut(BaseModel):
    a: VersionOut
    b: VersionOut
    total_a: Decimal
    total_b: Decimal
    delta_total: Decimal
    altas: list[CambioOut] = Field(default_factory=list)
    bajas: list[CambioOut] = Field(default_factory=list)
    cambios: list[CambioOut] = Field(default_factory=list)
    sin_cambios: int = 0
