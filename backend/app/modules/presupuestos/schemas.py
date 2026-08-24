import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrigenDato, TipoIVA
from app.modules.presupuestos.models import (
    NaturalezaConcepto,
    OrigenPrecio,
    TipoConcepto,
)


class FamiliaBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=32)
    nombre: str = Field(min_length=1, max_length=160)
    parent_id: uuid.UUID | None = None
    orden: int = 0


class FamiliaCreate(FamiliaBase):
    pass


class FamiliaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, min_length=1, max_length=32)
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    parent_id: uuid.UUID | None = None
    orden: int | None = None


class FamiliaOut(FamiliaBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creado_por_nombre: str | None = None


# --- Capítulos del banco de precios (Fase 50) ---


class CapituloBancoBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=32)
    resumen: str = Field(min_length=1, max_length=250)
    texto: str | None = None
    parent_id: uuid.UUID | None = None
    orden: int = 0


class CapituloBancoCreate(CapituloBancoBase):
    # El código se genera solo si no se da — la rejilla crea capítulos sin
    # pedirlo, igual que en un presupuesto.
    codigo: str | None = Field(default=None, max_length=32)


class CapituloBancoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, min_length=1, max_length=32)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    parent_id: uuid.UUID | None = None
    orden: int | None = None


class CapituloBancoOut(CapituloBancoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    creado_por_nombre: str | None = None


class ConceptoEnBanco(BaseModel):
    """Una ficha tal y como la pinta la rejilla del banco — no lleva el
    detalle completo (`ConceptoDetalle`), solo lo que se ve en una fila."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    tipo: TipoConcepto
    naturaleza: NaturalezaConcepto
    unidad: str
    resumen: str
    texto: str | None
    precio: Decimal
    precio_venta: Decimal | None
    origen_precio: OrigenPrecio
    familia_id: uuid.UUID | None
    capitulo_id: uuid.UUID | None
    orden: int
    activo: bool
    tiene_descompuesto: bool = False


class ArbolBanco(BaseModel):
    """SOLO el esqueleto: los capítulos y cuántas fichas cuelgan de cada uno.

    Las fichas NO viajan aquí. Un banco de precios real (un BEDEC, una tarifa
    de proveedor) trae decenas de miles: mandarlas todas eran 6 MB de JSON y,
    peor, decenas de miles de filas en el DOM que dejaban el navegador
    inservible. Se piden por capítulo con `/api/banco/fichas`, que sí pagina.
    """

    capitulos: list[CapituloBancoOut]
    # id de capítulo -> cuántas fichas tiene. La raíz va bajo la clave "".
    fichas_por_capitulo: dict[str, int]
    total_fichas: int


class PaginaFichas(BaseModel):
    items: list[ConceptoEnBanco]
    total: int


class AsignarFamiliaIn(BaseModel):
    """Asignación masiva o individual — la rejilla manda siempre una lista,
    aunque sea de un solo elemento."""

    concepto_ids: list[uuid.UUID] = Field(min_length=1)
    familia_id: uuid.UUID | None = None


class MoverAlCapituloIn(BaseModel):
    concepto_ids: list[uuid.UUID] = Field(min_length=1)
    capitulo_id: uuid.UUID | None = None


class MoverPorNaturalezaIn(BaseModel):
    """Mover TODAS las fichas de una naturaleza, sin enumerarlas — la usa la
    IA (Fase 50) para organizar el banco por naturaleza sin depender de
    ningún límite de búsqueda de texto."""

    naturaleza: NaturalezaConcepto
    capitulo_id: uuid.UUID | None = None


class PrecioSuministroBase(BaseModel):
    proveedor_id: uuid.UUID
    precio: Decimal = Field(ge=0, decimal_places=4)
    moneda: str = Field(default="EUR", min_length=3, max_length=3)
    descuento: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    cantidad_minima: Decimal | None = Field(default=None, ge=0)
    plazo_entrega_dias: int | None = Field(default=None, ge=0)
    referencia_proveedor: str | None = Field(default=None, max_length=60)
    vigente_desde: date
    vigente_hasta: date | None = None
    es_preferente: bool = False
    notas: str | None = None


class PrecioSuministroCreate(PrecioSuministroBase):
    origen_dato: OrigenDato = OrigenDato.MANUAL


class PrecioSuministroUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proveedor_id: uuid.UUID | None = None
    precio: Decimal | None = Field(default=None, ge=0)
    moneda: str | None = Field(default=None, min_length=3, max_length=3)
    descuento: Decimal | None = Field(default=None, ge=0, le=100)
    cantidad_minima: Decimal | None = Field(default=None, ge=0)
    plazo_entrega_dias: int | None = Field(default=None, ge=0)
    referencia_proveedor: str | None = None
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    es_preferente: bool | None = None
    notas: str | None = None


class PrecioSuministroOut(PrecioSuministroBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    concepto_id: uuid.UUID
    origen_dato: OrigenDato
    precio_neto: Decimal
    # Desnormalizado en la respuesta para no obligar al cliente a una segunda
    # llamada solo para pintar el nombre del proveedor en una tabla.
    proveedor_razon_social: str | None = None
    created_at: datetime
    updated_at: datetime


class ConceptoBase(BaseModel):
    tipo: TipoConcepto
    naturaleza: NaturalezaConcepto = NaturalezaConcepto.SIN_CLASIFICAR
    unidad: str = Field(default="ud", min_length=1, max_length=10)
    resumen: str = Field(min_length=1, max_length=250)
    texto: str | None = None
    origen_precio: OrigenPrecio = OrigenPrecio.MANUAL
    costes_indirectos: Decimal | None = Field(default=None, ge=0, le=100)
    fecha_precio: date | None = None
    ean: str | None = Field(default=None, max_length=14)
    familia_id: uuid.UUID | None = None
    precio_venta: Decimal | None = Field(default=None, ge=0)
    tipo_iva: TipoIVA = TipoIVA.GENERAL
    activo: bool = True


class ConceptoCreate(ConceptoBase):
    codigo: str | None = Field(default=None, max_length=32)
    # Solo se tiene en cuenta con origen_precio MANUAL; en los demás casos el
    # precio lo fija el cálculo.
    precio: Decimal = Field(default=Decimal("0.00"), ge=0)
    origen_dato: OrigenDato = OrigenDato.MANUAL


class ConceptoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: TipoConcepto | None = None
    naturaleza: NaturalezaConcepto | None = None
    unidad: str | None = Field(default=None, min_length=1, max_length=10)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    precio: Decimal | None = Field(default=None, ge=0)
    origen_precio: OrigenPrecio | None = None
    costes_indirectos: Decimal | None = Field(default=None, ge=0, le=100)
    fecha_precio: date | None = None
    ean: str | None = None
    familia_id: uuid.UUID | None = None
    capitulo_id: uuid.UUID | None = None
    orden: int | None = None
    precio_venta: Decimal | None = Field(default=None, ge=0)
    tipo_iva: TipoIVA | None = None
    activo: bool | None = None


class ConceptoOut(ConceptoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    precio: Decimal
    origen_dato: OrigenDato
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None


class LineaOut(BaseModel):
    """Una línea del descompuesto, con los datos del hijo ya resueltos."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hijo_id: uuid.UUID
    hijo_codigo: str
    hijo_resumen: str
    hijo_unidad: str
    hijo_tipo: TipoConcepto
    hijo_precio: Decimal
    rendimiento: Decimal
    factor: Decimal
    orden: int
    # rendimiento x factor x precio, redondeado a dos como en el papel.
    importe: Decimal


class LineaCreate(BaseModel):
    hijo_id: uuid.UUID
    rendimiento: Decimal = Field(gt=0)
    factor: Decimal = Field(default=Decimal("1"), gt=0)
    orden: int = 0


class LineaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rendimiento: Decimal | None = Field(default=None, gt=0)
    factor: Decimal | None = Field(default=None, gt=0)
    orden: int | None = None


class HistoricoPrecioOut(BaseModel):
    """Una entrada del histórico de precios: qué costes ha tenido el concepto."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    precio: Decimal
    origen_precio: OrigenPrecio
    fecha: datetime


class VentasOut(BaseModel):
    """Qué venta ha tenido el concepto, presupuestado y facturado por separado.

    `presupuestado` cuenta toda partida que lo referencia, esté o no
    certificada todavía; `facturado` solo lo que una certificación ya emitida
    ha reconocido como ejecutado. Son dos preguntas distintas y mezclarlas en
    un único número ocultaría cuánto de lo vendido está aún por cobrar.
    """

    presupuestado_partidas: int
    presupuestado_importe: Decimal
    facturado_lineas: int
    facturado_importe: Decimal


class ConceptoDetalle(ConceptoOut):
    lineas: list[LineaOut] = Field(default_factory=list)
    # Suma de las líneas, antes de aplicar costes indirectos.
    coste_directo: Decimal = Decimal("0.00")
    # simple / complejo / funcional, deducido de los hijos. No se almacena:
    # la clasificación se sigue de la estructura, no al revés.
    clase: str | None = None
    suministros: list[PrecioSuministroOut] = Field(default_factory=list)


class UsoOut(BaseModel):
    """Un concepto que contiene al consultado, directa o indirectamente."""

    id: uuid.UUID
    codigo: str
    resumen: str
    tipo: TipoConcepto
    precio: Decimal
    rendimiento: Decimal


class PartidaUsoOut(BaseModel):
    """Una partida de un presupuesto que usa este concepto."""

    id: uuid.UUID
    presupuesto_id: uuid.UUID
    presupuesto_nombre: str
    presupuesto_estado: str
    codigo: str
    resumen: str
    medicion: Decimal
    precio: Decimal
    importe: Decimal


class UsoCompletoOut(BaseModel):
    """Dónde participa un concepto: en descompuestos de otros conceptos, y en
    partidas de presupuestos concretos."""

    en_descomposiciones: list[UsoOut]
    en_partidas: list[PartidaUsoOut]


class NodoArbol(BaseModel):
    id: uuid.UUID
    codigo: str
    resumen: str
    unidad: str
    tipo: TipoConcepto
    precio: Decimal
    rendimiento: Decimal | None = None
    factor: Decimal | None = None
    importe: Decimal | None = None
    hijos: list["NodoArbol"] = Field(default_factory=list)


class ResultadoRecalculo(BaseModel):
    conceptos_modificados: int
    ids: list[uuid.UUID]
