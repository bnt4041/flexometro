"""Albaranes de material: lo que entra en obra desde un proveedor.

`AlbaranLinea.capitulo_id` es opcional y es lo que permite que el informe de
coste real vs. presupuestado compare por capítulo y no solo en total — la
misma idea que `ParteTrabajo.capitulo_id` en el módulo `obras`.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "compras"


class EstadoAlbaran(StrEnum):
    BORRADOR = "borrador"
    CONFORMADO = "conformado"
    FACTURADO = "facturado"


class Albaran(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un albarán de proveedor recibido en una obra."""

    __tablename__ = "albaran"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="albaran_codigo_unique"),
        Index("ix_compras_albaran_obra", "obra_id"),
        Index("ix_compras_albaran_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    # El número que trae el propio albarán del proveedor; no es el mismo
    # concepto que `codigo`, que es la referencia interna correlativa.
    numero_proveedor: Mapped[str | None] = mapped_column(String(60), nullable=True)

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("obras.obra.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )

    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoAlbaran] = mapped_column(
        enum_column(EstadoAlbaran, "estado_albaran"),
        nullable=False,
        default=EstadoAlbaran.BORRADOR,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    lineas: Mapped[list["AlbaranLinea"]] = relationship(
        back_populates="albaran",
        cascade="all, delete-orphan",
        order_by="AlbaranLinea.orden",
    )


class AlbaranLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del albarán: cantidad de un producto a un precio.

    `producto_id` es opcional, igual que `concepto_id` en `Partida`: un
    material fuera de catálogo (una compra puntual) se registra a mano con su
    descripción, sin forzar un alta en el catálogo solo para esta línea.
    """

    __tablename__ = "albaran_linea"
    __table_args__ = (
        Index("ix_compras_albaran_linea_albaran", "albaran_id"),
        Index("ix_compras_albaran_linea_capitulo", "capitulo_id"),
        {"schema": SCHEMA},
    )

    albaran_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.albaran.id", ondelete="CASCADE"),
        nullable=False,
    )
    producto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalogo.producto.id", ondelete="SET NULL"),
        nullable=True,
    )
    # SET NULL: igual que en ParteTrabajo, borrar el capítulo no borra el
    # coste ya incurrido, lo deja "sin asignar" en el informe.
    capitulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.capitulo.id", ondelete="SET NULL"),
        nullable=True,
    )

    descripcion: Mapped[str] = mapped_column(String(250), nullable=False)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    albaran: Mapped[Albaran] = relationship(back_populates="lineas")
