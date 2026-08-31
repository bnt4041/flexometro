"""Ajustes globales de la plataforma y de cada organización.

Cada tabla global es de una sola fila (`id` fijo a 1): no hace falta un
catálogo de configuraciones, solo un sitio donde guardar la de hoy y poder
cambiarla desde el panel sin tocar el `.env` ni reiniciar contenedores. Las
claves siguen teniendo un valor por defecto en `Settings` (`.env`) para que
el stack arranque sin esto configurado; cuando esta tabla tiene un valor,
manda ella (ver `app/modules/ia/configuracion.py`).
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
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
    # Visión de DeepSeek: modelo aparte del de texto, pero MISMA clave y misma
    # `base_url` — por eso no hay un `deepseek_vision_api_key` aquí.
    deepseek_vision_model: Mapped[str] = mapped_column(
        String(60), nullable=False, default="deepseek-v4-flash-vision-exp"
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


class ProveedorWhatsApp(StrEnum):
    """Con qué se habla con WhatsApp.

    `GOWA` es un puente contra WhatsApp Web: vale para enseñar el producto,
    pero detrás hay una cuenta personal y mandar automatismos por ahí acaba
    en cierre de la cuenta. `CLOUD` es la API oficial de Meta, que es lo que
    hay que usar funcionando como empresa — exige número de empresa, token y
    plantillas aprobadas.

    Es un ajuste y no una constante del código a propósito: pasar de uno a
    otro es cambiar esto y rellenar las credenciales, sin tocar el circuito
    de firma (ver `app/core/mensajeria/fabrica.py`)."""

    GOWA = "gowa"
    CLOUD = "cloud"


class ConfiguracionWhatsApp(TimestampMixin, Base):
    """WhatsApp saliente de la plataforma. Un solo número para todo
    Flexómetro, igual que el SMTP de plataforma: los mensajes salen como
    Flexómetro, no como cada organización.

    Las credenciales de los dos proveedores conviven en la misma fila y
    `proveedor` dice cuál manda. Se hace así, y no con una tabla por
    proveedor, para poder tener la API oficial ya configurada y probada antes
    de apagar el puente: el cambio es una palabra, no una migración."""

    __tablename__ = "configuracion_whatsapp"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    proveedor: Mapped[ProveedorWhatsApp] = mapped_column(
        enum_column(ProveedorWhatsApp, "proveedor_whatsapp"),
        nullable=False,
        default=ProveedorWhatsApp.GOWA,
    )
    #: Apagado de fábrica: sin esto, una instalación recién creada intentaría
    #: hablar con un proveedor que no existe.
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Prefijo que se pone a los teléfonos escritos sin él (España por defecto).
    prefijo_pais: Mapped[str] = mapped_column(String(5), nullable=False, default="34")

    # ── Puente WhatsApp Web (GOWA) ──────────────────────────────────────
    #: Dirección del puente, normalmente interna al stack (`http://gowa:3000`).
    base_url: Mapped[str | None] = mapped_column(String(200), nullable=True)
    usuario: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Solo necesario si el puente tiene varias cuentas vinculadas.
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── API oficial (Cloud API de Meta) ─────────────────────────────────
    cloud_phone_number_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cloud_token: Mapped[str | None] = mapped_column(String(400), nullable=True)
    cloud_version: Mapped[str] = mapped_column(String(10), nullable=False, default="v21.0")
    #: Nombres de las plantillas APROBADAS por Meta. Sin ellas la API oficial
    #: no deja iniciar conversación, así que no se pueden dar por supuestas.
    plantilla_aviso: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plantilla_codigo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idioma_plantilla: Mapped[str] = mapped_column(String(10), nullable=False, default="es")


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
