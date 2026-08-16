"""Ajustes globales de la plataforma y de cada organización.

Cada tabla global es de una sola fila (`id` fijo a 1): no hace falta un
catálogo de configuraciones, solo un sitio donde guardar la de hoy y poder
cambiarla desde el panel sin tocar el `.env` ni reiniciar contenedores. Las
claves siguen teniendo un valor por defecto en `Settings` (`.env`) para que
el stack arranque sin esto configurado; cuando esta tabla tiene un valor,
manda ella (ver `app/modules/ia/configuracion.py`).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin

SCHEMA = "core"


class ConfiguracionIA(TimestampMixin, Base):
    """Claves compartidas de DeepSeek/Gemini: la plataforma paga un único
    consumo y se lo repercute a cada organización según su tarifa — ninguna
    trae su propia clave."""

    __tablename__ = "configuracion_ia"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    deepseek_api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deepseek_model: Mapped[str] = mapped_column(
        String(60), nullable=False, default="deepseek-chat"
    )
    deepseek_base_url: Mapped[str] = mapped_column(
        String(200), nullable=False, default="https://api.deepseek.com"
    )
    gemini_api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gemini_model: Mapped[str] = mapped_column(
        String(60), nullable=False, default="gemini-flash-latest"
    )
    gemini_base_url: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="https://generativelanguage.googleapis.com/v1beta",
    )


class ConfiguracionSmtpPlataforma(TimestampMixin, Base):
    """SMTP con el que ERP Flexómetro envía su propio correo — altas de usuario,
    avisos de la plataforma. Distinto del SMTP que cada organización pueda
    configurar para el correo saliente de su propio negocio."""

    __tablename__ = "configuracion_smtp_plataforma"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    puerto: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    usuario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remitente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    usa_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ConfiguracionPasarelaPago(TimestampMixin, Base):
    """Credenciales de la pasarela de pago (Paddle). Se guardan ya para no
    tener que tocar el esquema cuando el webhook se conecte de verdad; hoy
    nada las usa en una llamada real a la API de Paddle."""

    __tablename__ = "configuracion_pasarela_pago"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    proveedor: Mapped[str] = mapped_column(String(20), nullable=False, default="paddle")
    api_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vendor_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ConfiguracionSmtpOrganizacion(TimestampMixin, Base):
    """SMTP propio de una organización, para el correo saliente de SU
    negocio (por ejemplo, enviar sus facturas a sus clientes). Fila opcional
    1:1 con `Organization`: sin ella, la organización simplemente no tiene
    correo saliente propio configurado todavía."""

    __tablename__ = "configuracion_smtp_organizacion"
    __table_args__ = {"schema": SCHEMA}

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.organization.id", ondelete="CASCADE"),
        primary_key=True,
    )
    host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    puerto: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    usuario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remitente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    usa_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
