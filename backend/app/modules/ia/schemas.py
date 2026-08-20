import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Lo que devuelve DeepSeek, antes de resolverlo contra el catálogo propio ---


class PartidaSugeridaLLM(BaseModel):
    codigo_existente: str | None = None
    resumen: str = Field(min_length=1, max_length=250)
    unidad: str = Field(default="ud", min_length=1, max_length=10)
    es_nueva: bool = False


class CapituloSugeridoLLM(BaseModel):
    resumen: str = Field(min_length=1, max_length=250)
    partidas: list[PartidaSugeridaLLM] = Field(default_factory=list)


class RespuestaLLM(BaseModel):
    """Esquema exacto que se le pide a DeepSeek en el prompt de sistema."""

    capitulos: list[CapituloSugeridoLLM] = Field(default_factory=list)


# --- Estadísticas propias (self-hosted, sin IA) ---


class CapituloFrecuenteOut(BaseModel):
    resumen: str
    veces: int


class PartidaFrecuenteOut(BaseModel):
    concepto_id: uuid.UUID
    codigo: str
    resumen: str
    unidad: str
    veces: int


class EstadisticasOut(BaseModel):
    generico: bool
    total_presupuestos: int
    capitulos: list[CapituloFrecuenteOut]
    partidas: list[PartidaFrecuenteOut]


# --- Sugerencia ya resuelta contra el cuadro de precios propio ---


class PartidaSugeridaOut(BaseModel):
    concepto_id: uuid.UUID | None
    codigo: str | None
    resumen: str
    unidad: str
    # Precio de referencia del concepto ya existente; None si es una partida
    # nueva propuesta por la IA (todavía sin tarifar).
    precio: Decimal | None
    es_nueva: bool


class CapituloSugeridoOut(BaseModel):
    resumen: str
    partidas: list[PartidaSugeridaOut]


class SolicitarSugerencia(BaseModel):
    tipo_obra: str = Field(min_length=1, max_length=120)
    descripcion: str | None = Field(default=None, max_length=500)


class SugerenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo_obra: str
    descripcion: str | None
    modelo: str
    plantilla_id: uuid.UUID | None
    created_at: datetime
    creado_por_nombre: str | None = None


class SugerenciaDetalle(SugerenciaOut):
    capitulos: list[CapituloSugeridoOut] = Field(default_factory=list)


# --- Crear plantilla a partir de una sugerencia revisada por el usuario ---


class PartidaPlantillaIn(BaseModel):
    # Si se indica, se reutiliza el concepto existente (revalidado contra la
    # organización). Si no, se crea un concepto nuevo con origen_dato=IA.
    concepto_id: uuid.UUID | None = None
    resumen: str = Field(min_length=1, max_length=250)
    unidad: str = Field(default="ud", min_length=1, max_length=10)


class CapituloPlantillaIn(BaseModel):
    resumen: str = Field(min_length=1, max_length=250)
    partidas: list[PartidaPlantillaIn] = Field(default_factory=list)


class CrearPlantillaDesdeSugerencia(BaseModel):
    nombre: str = Field(min_length=1, max_length=250)
    codigo: str | None = Field(default=None, max_length=32)
    capitulos: list[CapituloPlantillaIn] = Field(default_factory=list)


# --- Lectura de planos (Gemini) ---


class LineaSugeridaLLM(BaseModel):
    """Lo que devuelve Gemini para una línea, antes de calcular su parcial."""

    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


class RespuestaLecturaPlanoLLM(BaseModel):
    """Esquema exacto que se le pide a Gemini en el prompt."""

    lineas: list[LineaSugeridaLLM] = Field(default_factory=list)
    # Cosas del plano que Gemini no ha podido interpretar con confianza, en
    # vez de adivinar una cota. Se muestra tal cual al usuario.
    observaciones: str | None = None


class LineaMedicionSugeridaOut(BaseModel):
    comentario: str | None
    uds: Decimal | None
    longitud: Decimal | None
    anchura: Decimal | None
    altura: Decimal | None
    # Calculado localmente con las mismas reglas que el resto de la app —
    # nunca se confía en una cuenta que haga el LLM.
    parcial: Decimal


class LecturaPlanoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID | None
    fichero_nombre: str
    modelo: str
    observaciones: str | None
    aplicada_en: datetime | None
    created_at: datetime
    creado_por_nombre: str | None = None


class LecturaPlanoDetalle(LecturaPlanoOut):
    lineas: list[LineaMedicionSugeridaOut] = Field(default_factory=list)


class AplicarLecturaPlano(BaseModel):
    lineas: list[LineaSugeridaLLM] = Field(default_factory=list)


# --- Ayuda con IA sobre una línea del presupuesto: conversación con acceso
# de solo lectura a toda la cuenta (buscar en otros presupuestos, otras
# partidas) y una propuesta de acción que el usuario tiene que confirmar
# antes de que se ejecute — nunca escribe nada por su cuenta. ---


class ContextoAyudaLinea(BaseModel):
    tipo: Literal["capitulo", "partida"]
    codigo: str | None = None
    resumen: str = Field(min_length=1, max_length=250)
    unidad: str | None = None
    precio: Decimal | None = None
    presupuesto_id: uuid.UUID
    presupuesto_nombre: str


class MensajeConversacionIn(BaseModel):
    rol: Literal["user", "assistant"]
    contenido: str = Field(min_length=1, max_length=2000)


class ConversarAyudaLinea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contexto: ContextoAyudaLinea
    # El historial completo, turno a turno: la conversación no se guarda en
    # el servidor, así que quien pregunta manda cada vez todo lo dicho hasta
    # ahora (igual que cualquier API de chat sin estado).
    mensajes: list[MensajeConversacionIn] = Field(min_length=1, max_length=40)


class ComponentePropuestoOut(BaseModel):
    # Del banco de precios (el caso normal): resuelto contra un `Concepto`
    # que ya existe.
    concepto_id: uuid.UUID | None = None
    codigo: str | None = None
    resumen: str
    unidad: str
    rendimiento: Decimal
    # Personalizado (Fase 40): el usuario ha dado un precio de palabra (p. ej.
    # "el carpintero cobra 120€ por puerta") para algo que no está en el
    # banco de precios. `concepto_id` viene vacío; al confirmar, primero se
    # da de alta como concepto nuevo (origen manual) y luego se añade igual
    # que cualquier otro componente — no es una vía de escritura distinta.
    personalizado: bool = False
    precio: Decimal | None = None
    naturaleza: str | None = None


class PartidaPropuestaOut(BaseModel):
    """Una línea que la IA ha leído de un documento externo (Fase 39) y
    propone colgar de un capítulo nuevo — alzada, sin `concepto_id`: es una
    copia de lo que dice el papel, no un componente del banco de precios."""

    resumen: str
    unidad: str
    precio: Decimal
    medicion: Decimal = Decimal("1")


class PropuestaAccionOut(BaseModel):
    tipo: Literal["copiar_partida", "crear_partida", "importar_capitulo"]
    descripcion: str
    # copiar_partida:
    partida_id: uuid.UUID | None = None
    # crear_partida: una partida nueva (alzada), con estos componentes ya
    # resueltos contra el banco de precios propio.
    resumen: str | None = None
    unidad: str | None = None
    componentes: list[ComponentePropuestoOut] = Field(default_factory=list)
    # importar_capitulo: un capítulo nuevo entero, leído de un documento
    # externo (PDF, imagen o Excel) — cada partida es alzada, con el precio
    # que trae el documento, no del banco de precios propio.
    capitulo_resumen: str | None = None
    partidas_propuestas: list[PartidaPropuestaOut] = Field(default_factory=list)


class RespuestaAyudaLinea(BaseModel):
    respuesta: str
    propuesta: PropuestaAccionOut | None = None


# --- Conversación sobre un documento arrastrado (PDF/imagen/Excel) ---


class RespuestaDocumento(BaseModel):
    respuesta: str
    propuesta: PropuestaAccionOut | None = None
