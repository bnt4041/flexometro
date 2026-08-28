"""Esquemas de capítulos/partidas/mediciones/descomposición de la Factura de
venta (Fase 2). Calcado de `presupuestos.presupuesto_schemas`, con el
prefijo `Factura*` en vez de sin prefijo — mismo criterio ya usado en
`compras.pedido_schemas`.

`FacturaCapitulo` es de un solo nivel (sin subcapítulos, a diferencia de
`presupuestos.Capitulo`). Al ser una factura de venta siempre de cliente, el
descompuesto está siempre disponible: no hace falta ningún equivalente a
`DescomposicionNoDisponible`.
"""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.html_seguro import sanear_html
from app.modules.ia.schemas import MensajeConversacionIn
from app.modules.presupuestos.models import NaturalezaConcepto


class FacturaCapituloCreate(BaseModel):
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str = Field(min_length=1, max_length=250)
    texto: str | None = None
    orden: int = 0

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaCapituloUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    orden: int | None = None

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaCapituloOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_id: uuid.UUID
    codigo: str
    resumen: str
    texto: str | None
    orden: int


class FacturaCapituloConPartidas(FacturaCapituloOut):
    """El árbol completo de un capítulo, con sus partidas ya detalladas
    (mediciones incluidas) — lo que devuelve `GET /api/facturas/{id}/capitulos`."""

    partidas: list["FacturaPartidaDetalle"] = Field(default_factory=list)


class FacturaMedicionBase(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int = 0


class FacturaMedicionCreate(FacturaMedicionBase):
    pass


class FacturaMedicionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comentario: str | None = None
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int | None = None


class FacturaMedicionOut(FacturaMedicionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID
    parcial: Decimal


class FacturaPartidaCreate(BaseModel):
    concepto_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    orden: int = 0
    mediciones: list[FacturaMedicionCreate] = Field(default_factory=list)

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaPartidaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    medicion: Decimal | None = Field(default=None, ge=0)
    orden: int | None = None
    capitulo_id: uuid.UUID | None = None
    precio_venta: Decimal | None = Field(default=None, ge=0)
    venta_bloqueada: bool | None = None
    concepto_id: uuid.UUID | None = None

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaPartidaOut(BaseModel):
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
    precio_venta: Decimal = Decimal("0.00")
    venta_bloqueada: bool = False
    importe_venta: Decimal = Decimal("0.00")
    costes_indirectos: Decimal | None = None
    tiene_desglose: bool = False
    descomposicion_propia: bool = False


class FacturaPartidaDetalle(FacturaPartidaOut):
    mediciones: list[FacturaMedicionOut] = Field(default_factory=list)
    precio_cuadro: Decimal | None = None


class FacturaLineaDescomposicionOut(BaseModel):
    id: uuid.UUID
    hijo_id: uuid.UUID | None
    codigo: str
    resumen: str
    unidad: str
    naturaleza: str | None
    rendimiento: Decimal
    factor: Decimal
    precio: Decimal
    importe: Decimal


class FacturaDescomposicionOut(BaseModel):
    """`propia` distingue el descompuesto independizado de la partida del que
    todavía hereda del banco de precios (que se enseña en solo lectura)."""

    propia: bool
    lineas: list[FacturaLineaDescomposicionOut] = Field(default_factory=list)


class FacturaComponenteNuevo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    rendimiento: Decimal = Field(default=Decimal("1"), ge=0)
    factor: Decimal = Field(default=Decimal("1"), ge=0)


class FacturaCambioPrecioComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    precio: Decimal = Field(ge=0)
    # `partida`: solo esta. `factura`: todas las partidas de la misma
    # factura que lleven ese componente. El banco de precios no se toca.
    alcance: Literal["partida", "factura"] = "partida"


class FacturaCambioRendimientoComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    rendimiento: Decimal = Field(ge=0)


class FacturaCambioResumenComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    resumen: str = Field(min_length=1, max_length=250)


class FacturaCambioNaturalezaComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    naturaleza: NaturalezaConcepto


class FacturaCambioUnidadComponente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hijo_id: uuid.UUID
    unidad: str = Field(min_length=1, max_length=10)


class FacturaResultadoCambioPrecio(BaseModel):
    partidas_afectadas: int
    descomposicion: FacturaDescomposicionOut


# --- Copiar/mover (portapapeles) — Fase 5 ---
#
# Calcado de `presupuestos.presupuesto_schemas`, con el prefijo `Factura*` y
# sin `parent_id` en `FacturaPegarCapitulos`: `FacturaCapitulo` es de un solo
# nivel. `medicion_ids`, no `linea_ids`, para seguir la nomenclatura ya usada
# aquí (`FacturaMedicion`, `crear_medicion`...).


class FacturaPegarCapitulos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capitulo_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaPegarPartidas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partida_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaPegarMediciones(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medicion_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaPegarComponentesDescompuesto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linea_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaResultadoPegado(BaseModel):
    pegadas: int


# --- "Ayuda con IA" (Fase 4) — calcado de `ia.schemas.ContextoAyudaLinea`/
# `ConversarAyudaLinea`, con `factura_id`/`factura_codigo` en vez de
# `presupuesto_id`/`presupuesto_nombre` y sin el caso "ficha" — una factura
# no tiene fichas de banco de precios propias. Al ser una factura de venta
# siempre de cliente, no hace falta ningún equivalente a
# `DescomposicionNoDisponible` (a diferencia de `compras.pedido_schemas.
# ContextoAyudaPedido`).


class ContextoAyudaFactura(BaseModel):
    tipo: Literal["capitulo", "partida"]
    codigo: str | None = None
    resumen: str = Field(min_length=1, max_length=250)
    unidad: str | None = None
    precio: Decimal | None = None
    factura_id: uuid.UUID
    factura_codigo: str = Field(min_length=1, max_length=32)


class ConversarAyudaFactura(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contexto: ContextoAyudaFactura
    mensajes: list[MensajeConversacionIn] = Field(min_length=1, max_length=40)


# --- Aplicar un capítulo propuesto por la IA con descompuesto real (Fase 4)
# — calcado de `presupuestos.presupuesto_schemas.AplicarCapituloConComponentesIA`
# con el prefijo `Factura*`.


class FacturaComponentePropuestoIA(BaseModel):
    concepto_id: uuid.UUID | None = None
    rendimiento: Decimal
    personalizado: bool = False
    resumen: str | None = Field(default=None, max_length=250)
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    naturaleza: NaturalezaConcepto | None = None


class FacturaLineaMedicionPropuestaIA(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


class FacturaPartidaConComponentesIA(BaseModel):
    """Una partida bajo el capítulo nuevo: movida (`partida_id`, ya existe en
    la factura) o creada de cero (`resumen`/`unidad`/`componentes`)."""

    partida_id: uuid.UUID | None = None
    resumen: str | None = Field(default=None, max_length=250)
    unidad: str | None = Field(default=None, max_length=10)
    componentes: list[FacturaComponentePropuestoIA] = Field(default_factory=list)
    texto: str | None = None
    mediciones: list[FacturaLineaMedicionPropuestaIA] = Field(default_factory=list)

    @model_validator(mode="after")
    def _mover_xor_crear(self) -> "FacturaPartidaConComponentesIA":
        if self.partida_id is not None:
            return self
        if not self.resumen or not self.unidad or not self.componentes:
            raise ValueError(
                "Cada partida necesita partida_id (para moverla) o "
                "resumen + unidad + al menos un componente (para crearla)"
            )
        return self


class FacturaAplicarCapituloIA(BaseModel):
    capitulo_resumen: str = Field(min_length=1, max_length=250)
    partidas: list[FacturaPartidaConComponentesIA] = Field(min_length=1)
