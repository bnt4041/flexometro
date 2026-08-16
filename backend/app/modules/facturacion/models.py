"""Certificaciones, facturas y cobros.

`Certificacion` mide, obra a obra, cuánto se ha ejecutado de cada partida hasta
la fecha; `Factura` es el documento fiscal que se emite a partir de esa
certificación (o suelta, sin certificación); `Cobro` registra lo que
efectivamente ha entrado.

La numeración de `Factura` es la pieza que no admite descuido: una factura
emitida no se borra ni se renumera nunca — se anula, conservando su hueco en
la serie. Es requisito legal y es justo lo que exige Veri*Factu.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
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

from app.core.enums import TipoIVA, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.terceros.models import FormaPago

SCHEMA = "facturacion"


class EstadoCertificacion(StrEnum):
    BORRADOR = "borrador"
    EMITIDA = "emitida"


class EstadoFactura(StrEnum):
    BORRADOR = "borrador"
    EMITIDA = "emitida"
    ANULADA = "anulada"


class Certificacion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Certificación parcial de obra: medición acumulada a una fecha.

    `numero` es secuencial por obra (certificación nº 1, nº 2...), distinto del
    `codigo` interno correlativo de la organización. Una vez emitida queda
    bloqueada: generar una factura sobre una certificación que todavía puede
    cambiar de importe sería facturar un número que luego se movería solo.
    """

    __tablename__ = "certificacion"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="certificacion_codigo_unique"),
        UniqueConstraint("obra_id", "numero", name="certificacion_obra_numero_unique"),
        Index("ix_facturacion_certificacion_obra", "obra_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("obras.obra.id", ondelete="RESTRICT"),
        nullable=False,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoCertificacion] = mapped_column(
        enum_column(EstadoCertificacion, "estado_certificacion"),
        nullable=False,
        default=EstadoCertificacion.BORRADOR,
    )
    # Porcentaje retenido en garantía sobre el importe de esta certificación.
    # 0 por defecto: no todo el mundo retiene garantía, y no hay por qué
    # forzar el concepto a quien no lo necesita.
    retencion_garantia_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    lineas: Mapped[list["CertificacionLinea"]] = relationship(
        back_populates="certificacion",
        cascade="all, delete-orphan",
        order_by="CertificacionLinea.orden",
    )


class CertificacionLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Medición acumulada de una partida hasta esta certificación.

    Copia código, resumen, unidad y precio de la partida en el momento de
    certificar — el mismo motivo por el que `Partida` copia del `Concepto`: una
    certificación ya emitida no puede cambiar de importe porque alguien edite
    la partida después.
    """

    __tablename__ = "certificacion_linea"
    __table_args__ = (
        UniqueConstraint(
            "certificacion_id", "partida_id", name="certificacion_linea_partida_unique"
        ),
        Index("ix_facturacion_certificacion_linea_certificacion", "certificacion_id"),
        Index("ix_facturacion_certificacion_linea_partida", "partida_id"),
        {"schema": SCHEMA},
    )

    certificacion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.certificacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT: la partida certificada no puede desaparecer sin más de debajo
    # de una certificación ya hecha.
    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.partida.id", ondelete="RESTRICT"),
        nullable=False,
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    medicion_anterior: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    medicion_actual: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    # Materializados: periodo = actual - anterior, importe = periodo x precio.
    medicion_periodo: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    importe_periodo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    certificacion: Mapped[Certificacion] = relationship(back_populates="lineas")


class Factura(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """El documento fiscal. `serie` + `numero` son la numeración legal.

    `numero` se queda a NULL mientras la factura es un borrador: solo se
    consume un hueco de la serie al emitir, para que descartar un borrador no
    dilapide numeración. Emitida, ni se borra ni se renumera — se anula.
    """

    __tablename__ = "factura"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="factura_codigo_unique"),
        UniqueConstraint("organization_id", "serie", "numero", name="factura_serie_numero_unique"),
        Index("ix_facturacion_factura_obra", "obra_id"),
        Index("ix_facturacion_factura_cliente", "cliente_id"),
        Index("ix_facturacion_factura_certificacion", "certificacion_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    serie: Mapped[str] = mapped_column(String(10), nullable=False)
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("obras.obra.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # SET NULL, no RESTRICT: al llegar la certificación al final de su ciclo de
    # vida contable no tiene por qué atarse para siempre a la factura.
    certificacion_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.certificacion.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )

    concepto: Mapped[str] = mapped_column(String(250), nullable=False)
    fecha_emision: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    base_imponible: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tipo_iva: Mapped[TipoIVA] = mapped_column(
        enum_column(TipoIVA, "tipo_iva"), nullable=False, default=TipoIVA.GENERAL
    )
    # Obra subcontratada: la factura va sin IVA y lo autorrepercute el
    # destinatario (art. 84.Uno.2.º f LIVA). Se copia del presupuesto de la
    # obra al generar la factura.
    inversion_sujeto_pasivo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cuota_iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    estado: Mapped[EstadoFactura] = mapped_column(
        enum_column(EstadoFactura, "estado_factura"),
        nullable=False,
        default=EstadoFactura.BORRADOR,
    )
    motivo_anulacion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cuándo se notificó a n8n para el circuito Veri*Factu/Facturae. A NULL
    # significa "pendiente de enviar", incluida una factura emitida cuyo aviso
    # falló: el estado fiscal de la factura no depende de esta notificación.
    notificado_n8n_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    cobros: Mapped[list["Cobro"]] = relationship(
        back_populates="factura",
        cascade="all, delete-orphan",
        order_by="Cobro.fecha",
    )


class Cobro(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Un ingreso real contra una factura. Puede haber varios (cobro parcial)."""

    __tablename__ = "cobro"
    __table_args__ = (
        Index("ix_facturacion_cobro_factura", "factura_id"),
        {"schema": SCHEMA},
    )

    factura_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura.id", ondelete="CASCADE"),
        nullable=False,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    forma_pago: Mapped[FormaPago | None] = mapped_column(
        enum_column(FormaPago, "forma_pago"), nullable=True
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    factura: Mapped[Factura] = relationship(back_populates="cobros")
