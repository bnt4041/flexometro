import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

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
    # Cuántas empresas (organizaciones) puede tener la cuenta (Fase 41).
    # Autoservicio libre, no atado a la tarifa: el propio admin de
    # organización lo sube o lo baja desde Ajustes -> Empresas.
    max_organizaciones: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
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
    # Datos básicos de la empresa (Fase 40): de referencia visual — cabeceras
    # de documentos, plantillas Word — no fiscales (eso sigue siendo `cif`
    # más lo que ya tenga cada módulo, p. ej. `Tercero` para terceros).
    direccion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    codigo_postal: Mapped[str | None] = mapped_column(String(12), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provincia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    web: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram: Mapped[str | None] = mapped_column(String(255), nullable=True)
    facebook: Mapped[str | None] = mapped_column(String(255), nullable=True)
    twitter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Logo: objeto en MinIO (ver `app/core/storage.py`), no en esta tabla —
    # `logo_content_type` va aparte porque servirlo de vuelta necesita el
    # Content-Type original y MinIO no lo expone sin una segunda llamada.
    logo_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # HTML (Fase 41): texto enriquecido propio de esta empresa, no de la cuenta.
    politica_privacidad: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class Notificacion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Aviso persistente para una organización, o para un usuario concreto de
    ella. La campana de la barra superior.

    Hasta ahora la aplicación solo sabía mandar un correo o enseñar un aviso
    de cuatro segundos (`frontend/src/toast.tsx`). Esto es lo que hace falta
    para que a un proveedor que YA tiene Flexómetro le llegue una solicitud de
    precios dentro de su propia aplicación en vez de por un enlace externo.

    `destinatario_subject` a nulo = para toda la organización. Con valor, solo
    la ve ese usuario (el `sub` de Keycloak).

    `token_acceso` es el enlace del proveedor en claro, y solo lo llevan las
    notificaciones de solicitud de precios. Es deliberado: esta fila vive en
    la organización DEL PROVEEDOR y está protegida por RLS, así que tenerlo
    aquí es la misma exposición que tenerlo en su bandeja de correo — y es lo
    que permite aceptar la solicitud sin salir de la aplicación.
    """

    __tablename__ = "notificacion"
    __table_args__ = (
        Index("ix_core_notificacion_bandeja", "organization_id", "leida_en"),
        {"schema": "core"},
    )

    # Qué clase de aviso es, para saber qué acción ofrecer al abrirlo.
    tipo: Mapped[str] = mapped_column(String(48), nullable=False)
    destinatario_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)

    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    cuerpo: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Adónde lleva al pulsarla, dentro de la aplicación.
    enlace: Mapped[str | None] = mapped_column(String(500), nullable=True)
    importante: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    leida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Qué se hizo con ella, si tenía acción (aceptar una solicitud, por
    # ejemplo). Nulo = todavía no se ha decidido.
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    token_acceso: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # El presupuesto que se creó al aceptarla, si se aceptó.
    presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )
    # `{id de mi partida: id de la línea de la solicitud del emisor}`, para
    # poder devolver la oferta. Es el puente entre las dos organizaciones, y
    # vive aquí —en la del proveedor— porque una FK entre organizaciones
    # distintas no tendría sentido: son documentos de empresas diferentes.
    mapa_lineas: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Cuándo se le devolvió la oferta al emisor.
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
