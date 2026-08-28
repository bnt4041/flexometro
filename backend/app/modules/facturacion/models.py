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
from app.modules.core.tesoreria_models import CuentaFinanciera
from app.modules.presupuestos.models_presupuesto import MetodoCalculo
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

    # Jerarquía capítulo/partida/medición (Fase 1), misma estructura que
    # `Presupuesto` (ver `presupuestos.models_presupuesto`). Como una
    # factura de venta es siempre de cliente, el descompuesto está siempre
    # disponible en sus partidas.
    metodo_calculo: Mapped[MetodoCalculo] = mapped_column(
        enum_column(MetodoCalculo, "metodo_calculo"),
        nullable=False,
        default=MetodoCalculo.CLASICO,
    )
    porcentaje_metodo: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )

    cobros: Mapped[list["Cobro"]] = relationship(
        back_populates="factura",
        cascade="all, delete-orphan",
        order_by="Cobro.fecha",
    )
    capitulos: Mapped[list["FacturaCapitulo"]] = relationship(
        back_populates="factura",
        cascade="all, delete-orphan",
        order_by="FacturaCapitulo.orden",
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
    # Dónde entró el dinero (Fase 44). Distinto de `forma_pago`, que dice
    # cómo. RESTRICT: borrar la cuenta no debe borrar el rastro del cobro —
    # el servicio de tesorería lo impide antes de llegar aquí y ofrece
    # desactivarla en su lugar.
    cuenta_financiera_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.cuenta_financiera.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    factura: Mapped[Factura] = relationship(back_populates="cobros")
    # `selectin`: son una o dos filas por factura y hace falta el nombre
    # siempre que se serializa un cobro — con carga perezosa reventaría en
    # async (`MissingGreenlet`) justo al construir el `CobroOut`.
    cuenta_financiera: Mapped["CuentaFinanciera | None"] = relationship(lazy="selectin")

    @property
    def cuenta_financiera_nombre(self) -> str | None:
        return self.cuenta_financiera.nombre if self.cuenta_financiera else None


# --- Capítulos, partidas y mediciones de la factura (Fase 1) ---
#
# Misma jerarquía de tres niveles que `presupuestos.Capitulo`/`Partida`/
# `LineaMedicion` (ver ese módulo), calcada aquí porque una factura de venta
# es siempre de cliente y por tanto siempre puede llevar descompuesto propio
# en sus partidas — a diferencia de `compras.FacturaRecibida`, que al ser
# siempre de proveedor no tiene tabla de descomposición.


class FacturaCapitulo(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Nodo de la jerarquía de la factura. Un solo nivel plano, sin anidar
    subcapítulos — a diferencia de `presupuestos.Capitulo`."""

    __tablename__ = "factura_capitulo"
    __table_args__ = (
        Index("ix_facturacion_factura_capitulo_factura", "factura_id"),
        {"schema": SCHEMA},
    )

    factura_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura.id", ondelete="CASCADE"),
        nullable=False,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    factura: Mapped[Factura] = relationship(back_populates="capitulos")
    partidas: Mapped[list["FacturaPartida"]] = relationship(
        back_populates="capitulo",
        cascade="all, delete-orphan",
        order_by="FacturaPartida.orden",
    )


class FacturaPartida(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea presupuestada de la factura — mismo esquema que
    `presupuestos.Partida`. `concepto_id` es opcional: una partida alzada no
    se descompone y lleva su precio a mano."""

    __tablename__ = "factura_partida"
    __table_args__ = (
        Index("ix_facturacion_factura_partida_capitulo", "capitulo_id"),
        Index("ix_facturacion_factura_partida_factura", "factura_id"),
        Index("ix_facturacion_factura_partida_concepto", "concepto_id"),
        {"schema": SCHEMA},
    )

    factura_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura.id", ondelete="CASCADE"),
        nullable=False,
    )
    capitulo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura_capitulo.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    costes_indirectos: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    venta_bloqueada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    importe_venta: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )

    medicion: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    importe: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    capitulo: Mapped[FacturaCapitulo] = relationship(back_populates="partidas")
    mediciones: Mapped[list["FacturaMedicion"]] = relationship(
        back_populates="partida",
        cascade="all, delete-orphan",
        order_by="FacturaMedicion.orden",
    )
    descomposicion: Mapped[list["FacturaPartidaDescomposicion"]] = relationship(
        back_populates="partida",
        cascade="all, delete-orphan",
        order_by="FacturaPartidaDescomposicion.orden",
    )


class FacturaMedicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del estado de mediciones de una partida de factura — mismo
    esquema que `presupuestos.LineaMedicion` (sin soporte de fórmulas)."""

    __tablename__ = "factura_medicion"
    __table_args__ = (
        Index("ix_facturacion_factura_medicion_partida", "partida_id"),
        {"schema": SCHEMA},
    )

    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura_partida.id", ondelete="CASCADE"),
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

    partida: Mapped[FacturaPartida] = relationship(back_populates="mediciones")


class FacturaPartidaDescomposicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Descompuesto propio de una partida de factura — mismo esquema que
    `presupuestos.PartidaDescomposicion`."""

    __tablename__ = "factura_partida_descomposicion"
    __table_args__ = (
        Index("ix_facturacion_factura_partida_descomposicion_partida", "partida_id"),
        Index("ix_facturacion_factura_partida_descomposicion_hijo", "hijo_id"),
        {"schema": SCHEMA},
    )

    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura_partida.id", ondelete="CASCADE"),
        nullable=False,
    )
    hijo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    naturaleza: Mapped[str | None] = mapped_column(String(32), nullable=True)

    rendimiento: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    factor: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("1")
    )
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    partida: Mapped[FacturaPartida] = relationship(back_populates="descomposicion")
