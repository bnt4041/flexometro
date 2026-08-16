"""Estructura del presupuesto: obra, capítulos, partidas y mediciones.

Tablas propias, no tipos de `Concepto`. Una partida lleva datos que solo tienen
sentido dentro de su presupuesto —su medición, su sitio en un capítulo concreto
y el precio con el que se cerró—, así que el mismo unitario usado en dos obras
necesitaría dos filas de concepto. Sería llenar el cuadro de precios de
casi-duplicados, el mismo problema que evitamos separando `producto` de
`concepto`.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

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
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrigenDato, TipoIVA, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "presupuestos"


class EstadoPresupuesto(StrEnum):
    BORRADOR = "borrador"
    EMITIDO = "emitido"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    CANCELADO = "cancelado"


# Estados en los que el presupuesto deja de seguir al cuadro de precios.
ESTADOS_BLOQUEADOS = frozenset(
    {
        EstadoPresupuesto.EMITIDO,
        EstadoPresupuesto.APROBADO,
        EstadoPresupuesto.RECHAZADO,
        EstadoPresupuesto.CANCELADO,
    }
)


class Presupuesto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "presupuesto"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="presupuesto_codigo_unique"),
        Index("ix_presupuestos_presupuesto_estado", "organization_id", "estado"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Versiones ---
    # Las versiones de un mismo presupuesto se agrupan por `raiz_id`, que
    # apunta a la primera. En la primera es nulo: ella misma es la raíz.
    raiz_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- Plantillas ---
    # Una plantilla es un presupuesto como cualquier otro, marcado. Versionar e
    # instanciar una plantilla son la misma operación —copia profunda del
    # árbol—, así que no hacen falta tablas paralelas para lo mismo.
    es_plantilla: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Clasificación libre del tipo de obra ("rehabilitación de fachada",
    # "reforma integral"...). Es también la semilla del histórico sobre el que
    # trabajará la sugerencia de patrones por IA.
    tipo_obra: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    emplazamiento: Mapped[str | None] = mapped_column(String(250), nullable=True)

    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    validez_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[EstadoPresupuesto] = mapped_column(
        enum_column(EstadoPresupuesto, "estado_presupuesto"),
        nullable=False,
        default=EstadoPresupuesto.BORRADOR,
    )

    # Porcentajes del encadenado PEM -> PEC. Los valores por defecto son los
    # habituales de la contratación pública española (RD 1098/2001): 13 % de
    # gastos generales y 6 % de beneficio industrial.
    gastos_generales: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("13.00")
    )
    beneficio_industrial: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("6.00")
    )
    tipo_iva: Mapped[TipoIVA] = mapped_column(
        enum_column(TipoIVA, "tipo_iva"), nullable=False, default=TipoIVA.GENERAL
    )
    # En obra subcontratada la factura va sin IVA y lo autorrepercute el
    # destinatario (art. 84.Uno.2.º f LIVA).
    inversion_sujeto_pasivo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Mientras está a false, las partidas siguen al cuadro de precios en
    # cascada. Se pone a true al salir de borrador: un presupuesto emitido no
    # puede moverse solo bajo los pies de quien lo firmó.
    precios_bloqueados: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )

    capitulos: Mapped[list["Capitulo"]] = relationship(
        back_populates="presupuesto", cascade="all, delete-orphan"
    )


class Capitulo(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Nodo de la jerarquía del presupuesto. Profundidad libre."""

    __tablename__ = "capitulo"
    __table_args__ = (
        Index("ix_presupuestos_capitulo_presupuesto", "presupuesto_id"),
        Index("ix_presupuestos_capitulo_parent", "parent_id"),
        {"schema": SCHEMA},
    )

    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.presupuesto.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo.id", ondelete="CASCADE"),
        nullable=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    presupuesto: Mapped[Presupuesto] = relationship(back_populates="capitulos")
    partidas: Mapped[list["Partida"]] = relationship(
        back_populates="capitulo",
        cascade="all, delete-orphan",
        order_by="Partida.orden",
    )


class Partida(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea presupuestada: un precio unitario con su medición.

    `concepto_id` es opcional a propósito: una partida alzada no se descompone
    y lleva su precio a mano, y es algo corriente en un presupuesto real.
    """

    __tablename__ = "partida"
    __table_args__ = (
        Index("ix_presupuestos_partida_capitulo", "capitulo_id"),
        Index("ix_presupuestos_partida_presupuesto", "presupuesto_id"),
        Index("ix_presupuestos_partida_concepto", "concepto_id"),
        {"schema": SCHEMA},
    )

    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.presupuesto.id", ondelete="CASCADE"),
        nullable=False,
    )
    capitulo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        # SET NULL, no RESTRICT: borrar un unitario del cuadro no debe impedir
        # consultar un presupuesto ya cerrado; la partida conserva su copia.
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Copia de los datos del concepto en el momento de insertarlo. Es lo que
    # permite que un presupuesto emitido siga diciendo lo que decía.
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )

    # Materializados: cambian solo al tocar la medición o el precio.
    medicion: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    importe: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    capitulo: Mapped[Capitulo] = relationship(back_populates="partidas")
    lineas: Mapped[list["LineaMedicion"]] = relationship(
        back_populates="partida",
        cascade="all, delete-orphan",
        order_by="LineaMedicion.orden",
    )


class LineaMedicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del estado de mediciones.

    Réplica del registro ~M de FIEBDC-3: comentario, unidades, longitud,
    anchura (latitud en la norma) y altura. El parcial es el producto de los
    que estén informados; los que no lo estén valen 1, no 0 — una línea con
    solo `uds = 5` mide 5, no 0.
    """

    __tablename__ = "linea_medicion"
    __table_args__ = (
        Index("ix_presupuestos_linea_medicion_partida", "partida_id"),
        {"schema": SCHEMA},
    )

    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.partida.id", ondelete="CASCADE"),
        nullable=False,
    )
    comentario: Mapped[str | None] = mapped_column(String(250), nullable=True)
    uds: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    longitud: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    anchura: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    altura: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    parcial: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    partida: Mapped[Partida] = relationship(back_populates="lineas")
