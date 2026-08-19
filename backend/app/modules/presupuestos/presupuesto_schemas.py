import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OrigenDato, TipoIVA
from app.modules.presupuestos.models_presupuesto import EstadoPresupuesto, MetodoCalculo


class LineaMedicionBase(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int = 0
    # Con fórmula (Fase 37), el parcial sale de la expresión y de estos valores.
    formula_id: uuid.UUID | None = None
    formula_valores: dict[str, Decimal] = Field(default_factory=dict)


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
    # Ponerlo a null quita la fórmula y la línea vuelve a medirse por el
    # producto de longitud/anchura/altura.
    formula_id: uuid.UUID | None = None
    formula_valores: dict[str, Decimal] | None = None


class LineaMedicionOut(LineaMedicionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID
    parcial: Decimal
    formula_expresion: str | None = None


# --- Fórmulas de medición (Fase 37) ---


class FormulaMedicionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    expresion: str
    descripcion: str | None
    orden: int
    activa: bool
    # Las variables se deducen de la expresión, no se guardan: así no pueden
    # desincronizarse al editarla.
    variables: list[str] = Field(default_factory=list)


class FormulaMedicionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    expresion: str = Field(min_length=1, max_length=500)
    descripcion: str | None = Field(default=None, max_length=250)
    orden: int = 0


class FormulaMedicionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    expresion: str | None = Field(default=None, min_length=1, max_length=500)
    descripcion: str | None = Field(default=None, max_length=250)
    orden: int | None = None
    activa: bool | None = None


class ProbarFormulaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expresion: str = Field(min_length=1, max_length=500)
    valores: dict[str, Decimal] = Field(default_factory=dict)


class ProbarFormulaOut(BaseModel):
    variables: list[str]
    resultado: Decimal


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
    # Solo se admite en partidas SIN líneas de medición: con líneas, la
    # medición es la suma de sus parciales y escribirla a mano sería una
    # mentira que el siguiente recálculo borraría. Ver `actualizar_partida`.
    medicion: Decimal | None = Field(default=None, ge=0)
    orden: int | None = None
    capitulo_id: uuid.UUID | None = None
    precio_venta: Decimal | None = Field(default=None, ge=0)
    venta_bloqueada: bool | None = None
    # Ponerlo a null suelta la partida del banco de precios (pasa a alzada):
    # conserva su copia de código/descripción/precio, pero deja de seguir la
    # cascada del cuadro.
    concepto_id: uuid.UUID | None = None


class ConvertirLinea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["capitulo", "partida"]


# --- Descompuesto de la partida (Fase 34) ---


class LineaDescomposicionOut(BaseModel):
    id: uuid.UUID
    hijo_id: uuid.UUID | None
    codigo: str
    resumen: str
    unidad: str
    rendimiento: Decimal
    factor: Decimal
    precio: Decimal
    importe: Decimal


class DescomposicionPartidaOut(BaseModel):
    """`propia` distingue el descompuesto independizado de la partida del que
    todavía hereda del banco de precios (que se enseña en solo lectura)."""

    propia: bool
    lineas: list[LineaDescomposicionOut] = Field(default_factory=list)


class CambioPrecioComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    precio: Decimal = Field(ge=0)
    # `partida`: solo esta. `presupuesto`: todas las del mismo presupuesto que
    # lleven ese componente. El banco de precios no se toca en ningún caso.
    alcance: Literal["partida", "presupuesto"] = "partida"


class CambioRendimientoComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    rendimiento: Decimal = Field(ge=0)


class ComponenteNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    rendimiento: Decimal = Field(default=Decimal("1"), ge=0)
    factor: Decimal = Field(default=Decimal("1"), ge=0)


class ResultadoCambioPrecio(BaseModel):
    partidas_afectadas: int
    # El descompuesto ya recalculado: evita que el cliente tenga que volver a
    # pedirlo y se cruce con el commit, que ocurre tras enviar la respuesta.
    descomposicion: DescomposicionPartidaOut


# --- Reajuste del presupuesto (Fase 36) ---


class ReajusteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # `importe`: quiero que el presupuesto totalice X (sin IVA).
    # `margen`: quiero un margen del X % sobre la venta.
    tipo: Literal["importe", "margen"]
    valor: Decimal = Field(gt=0)
    # En falso solo se simula: es lo que alimenta la vista previa.
    aplicar: bool = False


class LineaReajusteOut(BaseModel):
    partida_id: uuid.UUID
    codigo: str
    resumen: str
    bloqueada: bool
    coste: Decimal
    venta_antes: Decimal
    venta_despues: Decimal
    importe_antes: Decimal
    importe_despues: Decimal


class ReajusteOut(BaseModel):
    aplicado: bool
    objetivo_venta: Decimal
    coste: Decimal
    venta_antes: Decimal
    venta_despues: Decimal
    # Los precios unitarios se redondean a dos decimales, así que la suma de
    # importes casi nunca cae exactamente en el objetivo. Se dice cuánto se
    # queda cerca en vez de forzar el cuadre retocando una partida.
    diferencia: Decimal
    margen_antes: Decimal
    margen_despues: Decimal
    factor: Decimal
    partidas_afectadas: int
    partidas_bloqueadas: int
    partidas_bajo_coste: int
    lineas: list[LineaReajusteOut] = Field(default_factory=list)


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
    # --- Venta (Fase 35) ---
    precio_venta: Decimal = Decimal("0.00")
    venta_bloqueada: bool = False
    importe_venta: Decimal = Decimal("0.00")
    # `perdida` | `bajo` | `ok` — el semáforo de la rejilla.
    estado_venta: str = "ok"
    # Solo lo llevan las partidas con descompuesto propio (Fase 34).
    costes_indirectos: Decimal | None = None
    # Si tiene líneas de medición, la medición es su suma y no se puede
    # teclear directamente en la rejilla (Fase 33).
    tiene_desglose: bool = False
    # Se ha independizado del banco de precios y su precio sale de su propio
    # descompuesto (Fase 34).
    descomposicion_propia: bool = False


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
    metodo: MetodoCalculo = MetodoCalculo.CLASICO
    porcentaje_metodo: Decimal = Decimal("0.00")
    coste: Decimal = Decimal("0.00")
    pem: Decimal
    gastos_generales: Decimal
    beneficio_industrial: Decimal
    # Diferencia entre el encadenado teórico y la venta real, que aparece
    # cuando hay partidas con la venta bloqueada a mano (Fase 35).
    ajuste_manual: Decimal = Decimal("0.00")
    incremento: Decimal = Decimal("0.00")
    venta_sin_iva: Decimal = Decimal("0.00")
    pec_sin_iva: Decimal
    porcentaje_iva: Decimal
    iva: Decimal
    total: Decimal
    margen: Decimal = Decimal("0.00")
    margen_pct: Decimal = Decimal("0.00")


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
    metodo_calculo: MetodoCalculo = MetodoCalculo.CLASICO
    porcentaje_metodo: Decimal = Field(default=Decimal("0.00"), ge=0, le=99.99)
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
    metodo_calculo: MetodoCalculo | None = None
    porcentaje_metodo: Decimal | None = Field(default=None, ge=0, le=99.99)
    precios_bloqueados: bool | None = None
    tipo_obra: str | None = Field(default=None, max_length=120)
    notas: str | None = None
    responsable_subject: str | None = Field(default=None, max_length=120)
    responsable_nombre: str | None = Field(default=None, max_length=200)


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
    responsable_subject: str | None = None
    responsable_nombre: str | None = None


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


# --- Edición por lotes (Fase 33: rejilla por teclado) ---


class CambioLinea(BaseModel):
    """Un cambio de celda sobre una línea del presupuesto.

    Los campos no enviados no se tocan (`exclude_unset`), así que la rejilla
    puede mandar solo lo que el usuario ha editado de verdad.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    tipo: Literal["capitulo", "partida"]
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    medicion: Decimal | None = Field(default=None, ge=0)
    precio_venta: Decimal | None = Field(default=None, ge=0)
    venta_bloqueada: bool | None = None


class LoteLineas(BaseModel):
    """Varios cambios de celda en una sola petición.

    Escribir cientos de líneas a mano son cientos de ediciones de celda; una
    petición (y una cascada de recálculo) por cada una haría la rejilla
    inusable. El cliente acumula y manda por tandas.
    """

    model_config = ConfigDict(extra="forbid")

    cambios: list[CambioLinea] = Field(default_factory=list)


# --- Recursos agregados (Fase 31: widgets "Precios básicos" y "Recursos humanos") ---


class RecursoAgregado(BaseModel):
    concepto_id: uuid.UUID
    codigo: str
    resumen: str
    unidad: str
    cantidad: Decimal
    precio: Decimal
    importe: Decimal


class RecursosPresupuesto(BaseModel):
    materiales: list[RecursoAgregado] = Field(default_factory=list)
    mano_obra: list[RecursoAgregado] = Field(default_factory=list)
    horas_totales: Decimal


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
