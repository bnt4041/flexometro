"""Esquemas de capítulos/partidas/mediciones de la Factura recibida (de
proveedor, Fase 2). Calcado de `presupuestos.presupuesto_schemas`, con el
prefijo `FacturaRecibida*`.

Sin descomposición ni venta: una factura recibida es siempre de proveedor,
así que la partida es siempre alzada — `precio` es directamente lo que cobra
el proveedor, ya final. No hay tabla `factura_recibida_partida_
descomposicion` (no existe, no aplica nunca) ni columnas
`precio_venta`/`venta_bloqueada`/`importe_venta`/`costes_indirectos`.
"""

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.html_seguro import sanear_html


class FacturaRecibidaCapituloCreate(BaseModel):
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str = Field(min_length=1, max_length=250)
    texto: str | None = None
    orden: int = 0

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaRecibidaCapituloUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, min_length=1, max_length=250)
    texto: str | None = None
    orden: int | None = None

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaRecibidaCapituloOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_id: uuid.UUID
    codigo: str
    resumen: str
    texto: str | None
    orden: int


class FacturaRecibidaCapituloConPartidas(FacturaRecibidaCapituloOut):
    """El árbol completo de un capítulo, con sus partidas ya detalladas
    (mediciones incluidas) — lo que devuelve
    `GET /api/facturas-recibidas/{id}/capitulos`."""

    partidas: list["FacturaRecibidaPartidaDetalle"] = Field(default_factory=list)


class FacturaRecibidaMedicionBase(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int = 0


class FacturaRecibidaMedicionCreate(FacturaRecibidaMedicionBase):
    pass


class FacturaRecibidaMedicionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comentario: str | None = None
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None
    orden: int | None = None


class FacturaRecibidaMedicionOut(FacturaRecibidaMedicionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID
    parcial: Decimal


class FacturaRecibidaPartidaCreate(BaseModel):
    concepto_id: uuid.UUID | None = None
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    orden: int = 0
    mediciones: list[FacturaRecibidaMedicionCreate] = Field(default_factory=list)

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaRecibidaPartidaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    texto: str | None = None
    unidad: str | None = Field(default=None, max_length=10)
    precio: Decimal | None = Field(default=None, ge=0)
    medicion: Decimal | None = Field(default=None, ge=0)
    orden: int | None = None
    capitulo_id: uuid.UUID | None = None
    concepto_id: uuid.UUID | None = None

    @field_validator("texto")
    @classmethod
    def _sanear_texto(cls, valor: str | None) -> str | None:
        return sanear_html(valor)


class FacturaRecibidaPartidaOut(BaseModel):
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
    tiene_desglose: bool = False


class FacturaRecibidaPartidaDetalle(FacturaRecibidaPartidaOut):
    mediciones: list[FacturaRecibidaMedicionOut] = Field(default_factory=list)
    precio_cuadro: Decimal | None = None


# --- Copiar/mover (portapapeles) — Fase 5 ---
#
# Calcado de `presupuestos.presupuesto_schemas`, con el prefijo
# `FacturaRecibida*` y sin `parent_id` en `FacturaRecibidaPegarCapitulos`
# (`FacturaRecibidaCapitulo` es de un solo nivel). Sin equivalente a
# `PegarComponentesDescompuesto`: no hay descomposición en esta entidad.
# `medicion_ids`, no `linea_ids`, para seguir la nomenclatura ya usada aquí.


class FacturaRecibidaPegarCapitulos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capitulo_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaRecibidaPegarPartidas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partida_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaRecibidaPegarMediciones(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medicion_ids: list[uuid.UUID] = Field(min_length=1)
    alcance: Literal["copiar", "mover"]


class FacturaRecibidaResultadoPegado(BaseModel):
    pegadas: int
