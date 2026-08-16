"""Patrón de numeración de documentos, configurable por cuenta — Fase 16.

Dos tablas separadas a propósito: `PatronNumeracion` decide CÓMO se escribe
la referencia (el patrón con tokens); `ContadorDocumento` decide CUÁL es el
siguiente número. Separarlas evita tener que reinterpretar códigos ya
generados con un patrón antiguo si el patrón cambia más adelante — el
contador nunca se derriba de los códigos existentes vía regex, solo avanza.

Cubre el `codigo` interno de Presupuesto, Albarán y Factura — los tres son
un correlativo propio sin significado fiscal. `Factura.serie`/
`Factura.numero` (la numeración legal de verdad, ver el docstring de
`Factura` en `facturacion/models.py`) NUNCA pasan por aquí: siguen las
reglas de Veri*Factu/Facturae de la Fase 8 (correlativo por
organización+serie, nunca se reutiliza, ver
`facturacion/service.py::emitir_factura`), fuera del alcance de esta fase.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class TipoDocumentoNumeracion(StrEnum):
    PRESUPUESTO = "presupuesto"
    ALBARAN = "albaran"
    FACTURA = "factura"  # el `codigo` interno, NUNCA serie/numero — ver docstring del módulo.


class PatronNumeracion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patron_numeracion"
    __table_args__ = (
        UniqueConstraint("cuenta_id", "tipo_documento", name="patron_numeracion_unique"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.cuenta.id", ondelete="CASCADE"), nullable=False
    )
    tipo_documento: Mapped[TipoDocumentoNumeracion] = mapped_column(
        enum_column(TipoDocumentoNumeracion, "tipo_documento_numeracion"), nullable=False
    )
    patron: Mapped[str] = mapped_column(String(80), nullable=False)
    # Elegido por el tenant (Fase 14): avisamos si las organizaciones de la
    # cuenta tienen CIF distinto, mas no lo bloqueamos — es su
    # responsabilidad legal, no la nuestra (y este `codigo` no es fiscal de
    # todos modos, ver docstring del módulo).
    secuencia_compartida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContadorDocumento(UUIDPrimaryKeyMixin, Base):
    """El contador real. `ambito_id` es `organization_id` (secuencia propia)
    o `cuenta_id` (secuencia compartida) según `PatronNumeracion.
    secuencia_compartida` en el momento de pedir el siguiente número — no
    lleva FK a ninguna de las dos tablas porque puede apuntar a cualquiera
    de ellas."""

    __tablename__ = "contador_documento"
    __table_args__ = (
        UniqueConstraint("ambito_id", "tipo_documento", name="contador_documento_unique"),
        {"schema": SCHEMA},
    )

    ambito_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tipo_documento: Mapped[TipoDocumentoNumeracion] = mapped_column(
        enum_column(TipoDocumentoNumeracion, "tipo_documento_numeracion"), nullable=False
    )
    ultimo: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
