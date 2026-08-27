"""Contratos: formalizan el acuerdo de una obra.

Con el cliente (contrato de obra, sobre el presupuesto aprobado) o con un
proveedor (marco/subcontrata), según `tipo` — mismo objeto con `tipo`, igual
que ya hace `presupuestos.Presupuesto`.

Sin líneas: el desglose de precio vive en el `Presupuesto` que enlaza, si lo
hay (`presupuesto_id`, opcional). El contrato es el envoltorio legal —
fechas, estado, importe — no un segundo sitio para repetir partidas.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "contratos"


class TipoContrato(StrEnum):
    CLIENTE = "cliente"
    PROVEEDOR = "proveedor"


class EstadoContrato(StrEnum):
    BORRADOR = "borrador"
    FIRMADO = "firmado"
    RESCINDIDO = "rescindido"
    FINALIZADO = "finalizado"


class Contrato(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "contrato"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="contrato_codigo_unique"),
        Index("ix_contratos_contrato_obra", "obra_id"),
        Index("ix_contratos_contrato_cliente", "cliente_id"),
        Index("ix_contratos_contrato_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    tipo: Mapped[TipoContrato] = mapped_column(
        enum_column(TipoContrato, "tipo_contrato"), nullable=False
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("obras.obra.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Uno de los dos, según `tipo` — validado en el schema, no aquí: el
    # modelo no impone la regla de negocio, solo guarda lo que ya se validó.
    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=True,
    )
    proveedor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # El presupuesto que formaliza, si lo hay. SET NULL: borrar el
    # presupuesto no borra el contrato ya firmado.
    presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )

    fecha_firma: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoContrato] = mapped_column(
        enum_column(EstadoContrato, "estado_contrato"),
        nullable=False,
        default=EstadoContrato.BORRADOR,
    )
    # Informativo, no recalculado desde ningún desglose: es el importe
    # contratado tal cual figura en el documento.
    importe: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    retencion_garantia_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
