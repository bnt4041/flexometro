"""Facturación de la plataforma a sus organizaciones (tenants).

No confundir con `facturacion.Factura`/`Cobro`: aquello es lo que una
organización cobra a SUS clientes; esto es lo que la plataforma cobra a la
organización por usar el ERP. Vive en el schema `core` porque gira alrededor
de `Organization`, que ya vive aquí.

Estas tablas no llevan `OrganizationMixin` con RLS: las gestiona en exclusiva
el rol superadmin a través de `app/modules/core/billing_router.py`, nunca un
endpoint de negocio de una organización — el mismo motivo por el que
`organization_module` sí lleva RLS pero `organization` no.
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
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class ProveedorIA(StrEnum):
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"


class TipoDescuento(StrEnum):
    PORCENTAJE = "porcentaje"
    IMPORTE_FIJO = "importe_fijo"


class MotivoDescuento(StrEnum):
    """Por qué se dio el descuento — no cambia el cálculo (eso lo hacen
    `tipo`/`valor`/vigencia), es para poder filtrar y reportar cuánto se ha
    concedido por cada razón comercial."""

    PRIMER_MES_GRATIS = "primer_mes_gratis"
    FIDELIZACION = "fidelizacion"
    RETENCION = "retencion"
    CAMPANA = "campana"
    AUMENTO_MODULOS = "aumento_modulos"
    OTRO = "otro"


class Tarifa(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Plan de precios: cuánto cuesta cada módulo al mes y cada 1000 tokens
    de IA. Se asigna a una organización desde su ficha de administración."""

    __tablename__ = "tarifa"
    __table_args__ = (
        UniqueConstraint("nombre", name="tarifa_nombre_unique"),
        {"schema": SCHEMA},
    )

    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # El coste real de DeepSeek y Gemini no es el mismo, así que cada
    # proveedor lleva su propio precio por 1000 tokens.
    precio_1000_tokens_deepseek: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0.0000")
    )
    precio_1000_tokens_gemini: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0.0000")
    )

    modulos: Mapped[list["TarifaModulo"]] = relationship(
        back_populates="tarifa", cascade="all, delete-orphan", order_by="TarifaModulo.module_code"
    )
    descuentos: Mapped[list["Descuento"]] = relationship(
        back_populates="tarifa", cascade="all, delete-orphan"
    )


class TarifaModulo(UUIDPrimaryKeyMixin, Base):
    """Precio mensual de un módulo dentro de una tarifa concreta."""

    __tablename__ = "tarifa_modulo"
    __table_args__ = (
        UniqueConstraint("tarifa_id", "module_code", name="tarifa_modulo_unique"),
        {"schema": SCHEMA},
    )

    tarifa_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.tarifa.id", ondelete="CASCADE"),
        nullable=False,
    )
    # No es FK al registro de módulos: los módulos viven en código
    # (`app.core.modules.registry`), no en base de datos.
    module_code: Mapped[str] = mapped_column(String(64), nullable=False)
    precio_mensual: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )

    tarifa: Mapped[Tarifa] = relationship(back_populates="modulos")


class Descuento(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Un descuento de catálogo: se crea una vez (en la zona de Tarifas) y se
    puede aplicar a cualquier número de organizaciones — no pertenece en
    exclusiva a ninguna. `tarifa_id` es solo de agrupación/búsqueda (bajo qué
    tarifa aparece listado); `None` significa que es un descuento general, no
    ligado a ninguna tarifa en concreto.

    Qué organizaciones lo tienen aplicado y desde cuándo vive en
    `OrganizacionDescuento`, no aquí — aplicar y anular son acciones sobre esa
    tabla, nunca crean ni borran el descuento del catálogo.
    """

    __tablename__ = "descuento"
    __table_args__ = ({"schema": SCHEMA},)

    tarifa_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.tarifa.id", ondelete="CASCADE"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    motivo: Mapped[MotivoDescuento] = mapped_column(
        enum_column(MotivoDescuento, "motivo_descuento"),
        nullable=False,
        default=MotivoDescuento.OTRO,
    )
    tipo: Mapped[TipoDescuento] = mapped_column(
        enum_column(TipoDescuento, "tipo_descuento"), nullable=False
    )
    # Si es PORCENTAJE, 0-100. Si es IMPORTE_FIJO, importe en euros.
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Vigencia opcional: sin fechas, el descuento es indefinido mientras esté
    # aplicado (campaña con ventana de fechas fija, ej. "SUMMER 2026").
    vigente_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Si el catálogo lo da de baja, deja de poder aplicarse a nadie nuevo y
    # deja de contar en las organizaciones que ya lo tuvieran (ver
    # `aplicacion_vigente`); no borra las aplicaciones ya hechas, es su
    # histórico.
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tarifa: Mapped[Tarifa | None] = relationship(back_populates="descuentos")


class CuentaDescuento(UUIDPrimaryKeyMixin, Base):
    """Que una cuenta tiene aplicado un descuento del catálogo, desde cuándo,
    y si se ha anulado. Cada fila es un hecho histórico: aplicar el mismo
    descuento otra vez tras anularlo crea una fila nueva, no reutiliza la
    anterior — así el histórico completo queda intacto.

    Desde la Fase 14 la facturación SaaS es por Cuenta, no por Organización
    (varias organizaciones de la misma cuenta comparten un único contrato) —
    esta tabla se llamaba `organizacion_descuento` antes de esa fase."""

    __tablename__ = "cuenta_descuento"
    __table_args__ = (
        Index("ix_core_cuenta_descuento_cuenta", "cuenta_id"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.cuenta.id", ondelete="CASCADE"),
        nullable=False,
    )
    descuento_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.descuento.id", ondelete="CASCADE"),
        nullable=False,
    )
    aplicado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # NULL mientras sigue en vigor; se rellena al anularla. No hace falta un
    # booleano "vigente" aparte — se deriva de esta columna, igual que
    # `Factura.numero` deriva "emitida" de si es NULL.
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    descuento: Mapped[Descuento] = relationship()


class UsoIA(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Un evento de consumo de IA: cada llamada a DeepSeek o Gemini deja aquí
    cuántos tokens ha costado y quién la ha disparado, para poder medir y
    facturar por organización y auditar por usuario."""

    __tablename__ = "uso_ia"
    __table_args__ = (
        Index("ix_core_uso_ia_organization", "organization_id"),
        Index("ix_core_uso_ia_organization_created", "organization_id", "created_at"),
        {"schema": SCHEMA},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.organization.id", ondelete="CASCADE"),
        nullable=False,
    )
    # subject/username de Keycloak: los usuarios viven en Keycloak, no aquí.
    usuario_subject: Mapped[str] = mapped_column(String(120), nullable=False)
    usuario_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    proveedor: Mapped[ProveedorIA] = mapped_column(
        enum_column(ProveedorIA, "proveedor_ia"), nullable=False
    )
    modelo: Mapped[str] = mapped_column(String(60), nullable=False)
    tokens_entrada: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # A qué operación corresponde (sugerencia_patron.id, lectura_plano.id...),
    # libre porque cada módulo de IA tiene su propia entidad de origen.
    referencia: Mapped[str | None] = mapped_column(String(120), nullable=True)


class CobroSaas(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Un cobro de la plataforma a una cuenta (Fase 14: la facturación SaaS
    es por Cuenta, no por Organización — un contrato consolidado cubre
    todas sus organizaciones).

    `origen`/`referencia_externa` son el punto de enganche para Paddle: hoy
    se registran a mano (`origen='manual'`); cuando el webhook de Paddle esté
    conectado, creará estas mismas filas con `origen='paddle'` y su id de
    transacción en `referencia_externa`, sin cambiar el esquema.
    """

    __tablename__ = "cobro_saas"
    __table_args__ = (
        Index("ix_core_cobro_saas_cuenta", "cuenta_id"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.cuenta.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto: Mapped[str] = mapped_column(String(250), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    referencia_externa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
