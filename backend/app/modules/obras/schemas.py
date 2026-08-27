import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.obras.models import EstadoObra, EstadoTarea, PrioridadTarea, TipoVinculo


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


class VinculoPresupuestoOut(BaseModel):
    """Un presupuesto que se está ejecutando en la obra."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    presupuesto_id: uuid.UUID
    tipo: TipoVinculo
    fecha_vinculacion: date
    orden: int
    notas: str | None
    # Resueltos aparte en el router: el listado necesita enseñar de qué
    # presupuesto se trata sin pedirlo uno a uno.
    presupuesto_codigo: str = ""
    presupuesto_nombre: str = ""


class VincularPresupuestoIn(BaseModel):
    presupuesto_id: uuid.UUID
    tipo: TipoVinculo = TipoVinculo.ANEXO
    notas: str | None = None


class AceptarPresupuestoIn(BaseModel):
    """Aceptar un presupuesto: o arranca una obra nueva, o entra como anexo en
    una que ya existe. Exactamente uno de los dos."""

    obra_id: uuid.UUID | None = None
    obra_nombre: str | None = Field(default=None, min_length=1, max_length=250)
    obra_codigo: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _uno_de_los_dos(self):
        # Se limpia antes de decidir: `min_length` no ve un nombre en blanco
        # («   » lo pasa), y de ahí saldría una obra sin nombre. El código
        # vacío es lo mismo que no darlo — significa «numérala tú».
        if self.obra_nombre is not None:
            self.obra_nombre = self.obra_nombre.strip() or None
        if self.obra_codigo is not None:
            self.obra_codigo = self.obra_codigo.strip() or None
        if (self.obra_id is None) == (self.obra_nombre is None):
            raise ValueError(
                "Indica una obra existente (obra_id) o el nombre de una nueva (obra_nombre), no ambos"
            )
        return self


class AceptadoOut(BaseModel):
    obra_id: uuid.UUID
    obra_codigo: str
    obra_nombre: str
    tipo: TipoVinculo
    creada: bool
    mensaje: str


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


# ---------------------------------------------------------------------------
# El árbol de la obra
# ---------------------------------------------------------------------------


class MedicionObraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID
    comentario: str | None
    uds: Decimal | None
    longitud: Decimal | None
    anchura: Decimal | None
    altura: Decimal | None
    parcial: Decimal
    orden: int


class MedicionObraCreate(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


class MedicionObraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


class PartidaObraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    obra_id: uuid.UUID
    capitulo_id: uuid.UUID
    codigo: str
    resumen: str
    texto: str | None
    unidad: str
    precio: Decimal
    precio_venta: Decimal
    medicion: Decimal
    importe: Decimal
    importe_venta: Decimal
    orden: int
    origen_presupuesto_id: uuid.UUID | None
    origen_partida_id: uuid.UUID | None
    es_anexo: bool
    # De qué presupuesto viene, ya resuelto: la rejilla lo enseña en cada fila
    # y pedirlo aparte serían N consultas.
    origen_codigo: str | None = None
    tiene_desglose: bool = False


class PartidaObraDetalle(PartidaObraOut):
    lineas: list[MedicionObraOut] = Field(default_factory=list)


class PartidaObraCreate(BaseModel):
    resumen: str = Field(min_length=1, max_length=250)
    codigo: str | None = Field(default=None, max_length=32)
    unidad: str = Field(default="ud", max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    precio_venta: Decimal | None = Field(default=None, ge=0)
    medicion: Decimal | None = None
    orden: int | None = None


class PartidaObraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capitulo_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    precio_venta: Decimal | None = Field(default=None, ge=0)
    medicion: Decimal | None = None
    orden: int | None = None


class CapituloObraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    obra_id: uuid.UUID
    parent_id: uuid.UUID | None
    codigo: str
    resumen: str
    texto: str | None
    orden: int
    origen_presupuesto_id: uuid.UUID | None
    origen_capitulo_id: uuid.UUID | None
    es_anexo: bool
    origen_codigo: str | None = None


class NodoObraOut(CapituloObraOut):
    """Un capítulo con lo que cuelga de él. Los importes son acumulados."""

    importe: Decimal = Decimal("0.00")
    importe_venta: Decimal = Decimal("0.00")
    partidas: list[PartidaObraOut] = Field(default_factory=list)
    hijos: list["NodoObraOut"] = Field(default_factory=list)


class CapituloObraCreate(BaseModel):
    resumen: str = Field(min_length=1, max_length=250)
    codigo: str | None = Field(default=None, max_length=32)
    parent_id: uuid.UUID | None = None
    texto: str | None = None
    orden: int | None = None


class CapituloObraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    orden: int | None = None


class TotalesObraOut(BaseModel):
    """Lo contratado frente a lo que la obra dice ahora mismo."""

    coste: Decimal
    venta: Decimal
    # Solo lo marcado como anexo: es la desviación sobre el contrato inicial.
    coste_anexos: Decimal
    venta_anexos: Decimal


class ArbolObraOut(BaseModel):
    obra_id: uuid.UUID
    capitulos: list[NodoObraOut] = Field(default_factory=list)
    totales: TotalesObraOut


# ---------------------------------------------------------------------------
# Tareas de obra
# ---------------------------------------------------------------------------


class TareaBase(BaseModel):
    titulo: str = Field(min_length=1, max_length=250)
    descripcion: str | None = None
    responsable_id: uuid.UUID | None = None
    fecha_limite: date | None = None
    estado: EstadoTarea = EstadoTarea.PENDIENTE
    prioridad: PrioridadTarea = PrioridadTarea.NORMAL


class TareaCreate(TareaBase):
    pass


class TareaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str | None = Field(default=None, min_length=1, max_length=250)
    descripcion: str | None = None
    responsable_id: uuid.UUID | None = None
    fecha_limite: date | None = None
    estado: EstadoTarea | None = None
    prioridad: PrioridadTarea | None = None


class MoverTareaIn(BaseModel):
    """Lo que manda el tablero al soltar una tarjeta: columna y posición."""

    estado: EstadoTarea
    # Se recorta al hueco real en el servicio: la posición viene del navegador y
    # puede haber cambiado la columna mientras se arrastraba.
    posicion: int = Field(default=0, ge=0)


class TareaOut(TareaBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    obra_id: uuid.UUID
    orden: int
    completada_en: date | None
    created_at: datetime
    updated_at: datetime
    creado_por_nombre: str | None = None
    # Resuelto en el router: la tarjeta enseña el nombre, no el identificador.
    responsable_nombre: str | None = None


class PartidaAlzadaPropuestaIn(BaseModel):
    """Una partida propuesta por la IA al leer un documento — alzada, tal
    cual trae el precio el documento (la obra no lleva descompuesto)."""

    resumen: str = Field(min_length=1, max_length=250)
    unidad: str = Field(default="ud", max_length=10)
    precio: Decimal = Field(ge=0)
    medicion: Decimal = Decimal("1")


class AplicarPropuestaIAObra(BaseModel):
    """Confirmación de una propuesta `importar_capitulo` sobre el árbol de
    la obra: crea el capítulo (siempre anexo) y sus partidas alzadas de una
    vez — ver `aplicar_propuesta_ia` en presupuestos, mismo patrón."""

    capitulo_resumen: str = Field(min_length=1, max_length=250)
    partidas: list[PartidaAlzadaPropuestaIn] = Field(default_factory=list)


class LineaMedicionPropuestaIn(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


class AplicarMedicionesIAObra(BaseModel):
    """Confirmación de una propuesta `anadir_mediciones_partida` de la IA
    sobre una partida ya existente de la obra."""

    partida_id: uuid.UUID
    lineas: list[LineaMedicionPropuestaIn] = Field(default_factory=list)


class ResumenTareasObra(BaseModel):
    """Para el widget del cuadro de mandos."""

    pendientes: int
    en_curso: int
    hechas: int
    # Con fecha límite pasada y sin terminar. Una hecha tarde ya no pide nada.
    vencidas: int
