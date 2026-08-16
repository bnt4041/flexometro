"""Diccionario de referencia por cuenta — Fase 18.

Listas editables por el propio tenant (países, formas de pago...) en vez de
vocabularios fijos de código. `tipo` sigue siendo un enum cerrado (como
`TipoDocumentoNumeracion` en `numeracion_models.py`): añadir una CATEGORÍA
nueva de diccionario es una migración, pero las ENTRADAS de cada categoría
las gestiona el admin de organización sin tocar código.

`forma_pago` convive con el enum `FormaPago` de `terceros/models.py`, que
sigue siendo la fuente de verdad de qué valores acepta la base de datos en
`Tercero.forma_pago`/`CobroFactura.forma_pago` (columna con CHECK
constraint) — el diccionario solo decide qué etiqueta, orden y activación
usa la interfaz para esos mismos valores. Una entrada con `clave` fuera del
enum simplemente no podrá usarse en un tercero o un cobro (lo rechaza la
base de datos), no corrompe nada.
"""

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class TipoDiccionario(StrEnum):
    PAIS = "pais"
    FORMA_PAGO = "forma_pago"
    # Fase 20 — mismo patrón, más categorías al estilo Dolibarr:
    PROVINCIA = "provincia"
    UNIDAD_MEDIDA = "unidad_medida"
    FORMA_JURIDICA = "forma_juridica"
    TRATAMIENTO = "tratamiento"
    CARGO = "cargo"
    # Fase 23 — tablas de tipos/porcentajes, no solo etiquetas: usan `valor`.
    # `IVA` es solo de referencia/documentación: el % legal que de verdad se
    # aplica en presupuestos y facturas sigue viniendo de `TipoIVA`/
    # `TIPO_IVA_PORCENTAJE` en `app/core/enums.py` — un tenant no puede
    # romper su propio cálculo fiscal cambiando aquí un 21% por error.
    # `RECARGO_EQUIVALENCIA` es también solo de referencia por ahora: aplicar
    # el recargo automáticamente en una línea es una fase futura, todavía
    # no existe ni la marca "minorista con recargo" en el tercero.
    # `RETENCION` sí es una sugerencia real de verdad: el campo de la ficha
    # del tercero (`irpf_retencion`) sigue siendo un decimal libre, esto solo
    # ofrece valores habituales para no teclearlos de memoria.
    IVA = "iva"
    RECARGO_EQUIVALENCIA = "recargo_equivalencia"
    RETENCION = "retencion"


class EntradaDiccionario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entrada_diccionario"
    __table_args__ = (
        UniqueConstraint("cuenta_id", "tipo", "clave", name="entrada_diccionario_unique"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.cuenta.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[TipoDiccionario] = mapped_column(enum_column(TipoDiccionario, "tipo_diccionario"), nullable=False)
    clave: Mapped[str] = mapped_column(String(64), nullable=False)
    etiqueta: Mapped[str] = mapped_column(String(120), nullable=False)
    # Solo relevante para categorías de tipo/tabla-de-tasa (iva, recargo de
    # equivalencia, retención) — el porcentaje que representa la entrada.
    # `None` para diccionarios de simple etiqueta (país, provincia...).
    valor: Mapped[Decimal | None] = mapped_column(Numeric(7, 3), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
