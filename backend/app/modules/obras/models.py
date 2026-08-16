"""Ejecución de obra: la obra en sí, el personal propio y sus costes reales.

`Personal` son empleados de la organización, no terceros: un tercero
(cliente/proveedor/subcontratista) es una entidad externa, y la mano de obra
subcontratada ya se factura como compra a ese tercero. Personal es la plantilla
propia, la que genera coste de mano de obra día a día.

El patrón Asignación → ParteTrabajo replica a propósito el de Partida →
LineaMedicion: la asignación copia el coste/hora del trabajador en el momento
de asignarlo (igual que la partida copia el precio del concepto), así que subir
el coste/hora de alguien no reescribe el histórico de una obra ya cerrada; y el
parte de trabajo es a la asignación lo que la línea de medición es a la
partida, un registro día a día que se acumula en un coste materializado.
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "obras"


class EstadoObra(StrEnum):
    PLANIFICADA = "planificada"
    EN_EJECUCION = "en_ejecucion"
    PARALIZADA = "paralizada"
    FINALIZADA = "finalizada"
    CERRADA = "cerrada"


class Obra(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """La ejecución real de un presupuesto.

    Un presupuesto describe una oferta; una obra es su ejecución en curso, con
    sus propias fechas y su propio estado. Referencia una versión concreta del
    presupuesto —normalmente la aprobada—, de la que toma capítulos y partidas
    para comparar coste real contra presupuestado.
    """

    __tablename__ = "obra"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="obra_codigo_unique"),
        # Una obra por presupuesto: ejecutar la misma oferta dos veces no
        # tiene sentido de negocio, y confundiría la comparación de costes.
        UniqueConstraint("presupuesto_id", name="obra_presupuesto_unique"),
        Index("ix_obras_obra_estado", "organization_id", "estado"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)

    # RESTRICT: una obra en marcha no puede quedarse sin el presupuesto del
    # que saca su comparación de coste.
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    jefe_obra_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.personal.id", ondelete="SET NULL"),
        nullable=True,
    )

    estado: Mapped[EstadoObra] = mapped_column(
        enum_column(EstadoObra, "estado_obra"), nullable=False, default=EstadoObra.PLANIFICADA
    )
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin_real: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class Personal(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un trabajador propio de la organización."""

    __tablename__ = "personal"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="personal_codigo_unique"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Texto libre a propósito: "oficial 1a", "peón", "encargado"... no hace
    # falta un catálogo cerrado para una plantilla propia.
    categoria: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Coste para la empresa (no lo que se le paga en mano): salario más
    # cargas sociales prorrateadas por hora. Es el valor por defecto que se
    # copia al asignarlo a una obra.
    coste_hora: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class Asignacion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Que un trabajador está adscrito a una obra, con su coste congelado.

    `coste_hora` se copia de `Personal` al crear la asignación: es la misma
    razón por la que una `Partida` copia el precio del `Concepto` — que subir
    el coste de alguien no reescriba en silencio el coste histórico de una
    obra que ya se cerró.
    """

    __tablename__ = "asignacion"
    __table_args__ = (
        Index("ix_obras_asignacion_obra", "obra_id"),
        Index("ix_obras_asignacion_personal", "personal_id"),
        {"schema": SCHEMA},
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    personal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.personal.id", ondelete="RESTRICT"),
        nullable=False,
    )
    coste_hora: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    partes: Mapped[list["ParteTrabajo"]] = relationship(
        back_populates="asignacion",
        cascade="all, delete-orphan",
        order_by="ParteTrabajo.fecha",
    )


class ParteTrabajo(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Parte diario: horas reales de un trabajador en un día concreto.

    `coste` es `horas x coste_hora`, materializado en la fila para no
    recalcularlo en cada lectura del informe de coste real. `capitulo_id` es
    opcional: permite atribuir la mano de obra de ese día a un capítulo
    concreto del presupuesto de la obra, para que el informe compare por
    capítulo y no solo en total.
    """

    __tablename__ = "parte_trabajo"
    __table_args__ = (
        UniqueConstraint(
            "asignacion_id", "fecha", name="parte_trabajo_asignacion_fecha_unique"
        ),
        Index("ix_obras_parte_trabajo_asignacion", "asignacion_id"),
        Index("ix_obras_parte_trabajo_capitulo", "capitulo_id"),
        {"schema": SCHEMA},
    )

    asignacion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.asignacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL: si se borra el capítulo, el coste ya incurrido no desaparece,
    # pasa a "sin asignar" en el informe.
    capitulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.capitulo.id", ondelete="SET NULL"),
        nullable=True,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    horas: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    coste: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    asignacion: Mapped[Asignacion] = relationship(back_populates="partes")
