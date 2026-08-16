import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrigenDato, TipoIVA, TipoProducto, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "catalogo"


class Familia(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Clasificación arbórea del catálogo. Jerarquía libre por autorreferencia."""

    __tablename__ = "familia"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="familia_codigo_unique"),
        {"schema": SCHEMA},
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.familia.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hijos: Mapped[list["Familia"]] = relationship(
        back_populates="padre", cascade="save-update"
    )
    padre: Mapped["Familia | None"] = relationship(
        back_populates="hijos", remote_side="Familia.id"
    )


class Producto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Catálogo comercial y logístico: lo que se compra y lo que se vende.

    Deliberadamente separado del `concepto` de presupuestación (Fase 2). Un
    banco de precios FIEBDC-3 importado trae decenas de miles de conceptos que
    no tienen nada que hacer en el catálogo propio de la empresa; lo que sí los
    une es `PrecioSuministro`.
    """

    __tablename__ = "producto"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="producto_codigo_unique"),
        Index("ix_catalogo_producto_resumen", "organization_id", "resumen"),
        Index("ix_catalogo_producto_tipo", "organization_id", "tipo"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    tipo: Mapped[TipoProducto] = mapped_column(
        enum_column(TipoProducto, "tipo_producto"),
        nullable=False,
        default=TipoProducto.MATERIAL,
    )
    familia_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.familia.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # `resumen` es el texto corto que se imprime en presupuestos y albaranes;
    # el nombre viene de FIEBDC-3, donde el campo se llama así.
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Unidad en texto libre (ud, m, m2, m3, kg, h...), como en FIEBDC-3.
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")

    tipo_iva: Mapped[TipoIVA] = mapped_column(
        enum_column(TipoIVA, "tipo_iva"), nullable=False, default=TipoIVA.GENERAL
    )
    precio_venta: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    ean: Mapped[str | None] = mapped_column(String(14), nullable=True)

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )
    atributos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    familia: Mapped[Familia | None] = relationship()
    suministros: Mapped[list["PrecioSuministro"]] = relationship(
        back_populates="producto",
        cascade="all, delete-orphan",
        order_by="PrecioSuministro.vigente_desde.desc()",
    )


class PrecioSuministro(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Precio de un producto puesto por un proveedor concreto en una fecha.

    Primer eslabón de la cadena de Ramírez de Arellano. Cuatro decimales a
    propósito: las tarifas de proveedor llegan así (material a granel,
    tornillería), y el redondeo a dos decimales de la convención Presto se
    aplica al encadenar conceptos, a partir del precio básico. Redondear aquí
    metería error antes de empezar.
    """

    __tablename__ = "precio_suministro"
    __table_args__ = (
        Index("ix_catalogo_precio_suministro_producto", "organization_id", "producto_id"),
        Index("ix_catalogo_precio_suministro_proveedor", "organization_id", "proveedor_id"),
        # Como mucho una tarifa preferente por producto.
        Index(
            "uq_catalogo_precio_suministro_preferente",
            "producto_id",
            unique=True,
            postgresql_where=text("es_preferente"),
        ),
        {"schema": SCHEMA},
    )

    producto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.producto.id", ondelete="CASCADE"),
        nullable=False,
    )
    # FK entre schemas: es la dependencia catalogo -> terceros hecha explícita
    # en la base de datos, no solo en el registro de módulos.
    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )

    precio: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    descuento: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    cantidad_minima: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    plazo_entrega_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referencia_proveedor: Mapped[str | None] = mapped_column(String(60), nullable=True)

    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    es_preferente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    producto: Mapped[Producto] = relationship(back_populates="suministros")

    @property
    def precio_neto(self) -> Decimal:
        """Precio con el descuento de tarifa aplicado, sin redondear a dos."""
        return (self.precio * (Decimal("100") - self.descuento) / Decimal("100")).quantize(
            Decimal("0.0001")
        )
