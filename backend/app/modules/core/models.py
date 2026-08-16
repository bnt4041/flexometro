import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class Cuenta(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """La cuenta de cliente (Fase 14): un contrato de pago que puede agrupar
    varias organizaciones (empresas/CIFs) bajo un mismo cliente — por
    ejemplo, un grupo empresarial con varias sociedades. La facturación de
    la plataforma (tarifa asignada, cobros, coste estimado, descuentos)
    vive AQUÍ, no en `Organization`: varias organizaciones de la misma
    cuenta comparten un único contrato y una única factura consolidada.

    Los datos de negocio de cada organización (presupuestos, terceros,
    facturas de sus clientes...) siguen SIEMPRE aislados por organización —
    Cuenta nunca es un límite de aislamiento de datos operativos, solo de
    facturación y (desde la Fase 15, opt-in) de maestros compartidos."""

    __tablename__ = "cuenta"
    __table_args__ = {"schema": SCHEMA}

    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Plan de precios asignado. SET NULL: borrar una tarifa no debe borrar ni
    # bloquear a las cuentas que la tenían asignada, solo dejarlas sin tarifa
    # hasta que se les asigne otra.
    tarifa_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.tarifa.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Columna propia (no en `settings`) a propósito: gobierna una política
    # RLS (Fase 15, ver `app/core/rls.py`) y un booleano de seguridad no
    # debe vivir enterrado en JSON, donde un valor ausente/mal tipado se
    # confundiría en silencio con "desactivado".
    compartir_maestros: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Reservado para preferencias a nivel cuenta que NO gobiernan seguridad:
    # patrones de numeración por tipo de documento (Fase 16)... cada fase
    # rellena su propia clave, sin migrar columnas nuevas por cada
    # preferencia suelta.
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    organizaciones: Mapped[list["Organization"]] = relationship(back_populates="cuenta")


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Una empresa/CIF dentro de una cuenta. Sigue siendo la raíz del
    aislamiento de datos de negocio (`OrganizationMixin` en toda tabla de
    negocio) — Cuenta agrupa por encima, pero nunca sustituye este límite."""

    __tablename__ = "organization"
    __table_args__ = {"schema": SCHEMA}

    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Preferencias del tenant (política de redondeo, divisa, IVA por defecto...).
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # RESTRICT, no CASCADE: no hay (ni se ha pedido) un flujo de "borrar
    # cuenta" que deba arrastrar organizaciones y su histórico de negocio.
    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.cuenta.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    modules: Mapped[list["OrganizationModule"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    cuenta: Mapped[Cuenta] = relationship(back_populates="organizaciones")


class OrganizationModule(UUIDPrimaryKeyMixin, Base):
    """Qué módulos tiene activos cada organización.

    `module_code` no es una FK: los módulos viven en el registro de código, no
    en base de datos. Un código huérfano (módulo retirado) simplemente se ignora
    al resolver la activación.
    """

    __tablename__ = "organization_module"
    __table_args__ = (
        UniqueConstraint("organization_id", "module_code", name="organization_module_unique"),
        {"schema": SCHEMA},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_code: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="modules")
