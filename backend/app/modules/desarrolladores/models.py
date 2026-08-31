"""Claves de API y webhooks: cómo entra y sale la aplicación de sí misma."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import (
    AutoriaMixin,
    Base,
    OrganizationMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.modules.desarrolladores.enums import EstadoEntrega

SCHEMA = "desarrolladores"


class ClaveApi(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Una llave para entrar sin navegador.

    Del secreto solo se guarda su SHA-256, igual que los enlaces de firma: si
    se filtrara la tabla, las claves no serían utilizables. El `prefijo` sí
    va en claro y es lo que se enseña en pantalla («flx_a1b2c3d4…») para poder
    reconocer cuál es cuál sin exponer nada — y además es por donde se busca,
    para no tener que comparar contra todas las filas en cada petición.

    Los ámbitos usan el MISMO modelo de permisos que las personas
    (`{"obras": {"ver": "todos", "crear": "ninguno", …}}`), así que
    `require_permiso` funciona igual venga quien venga. Una integración no
    puede hacer nada que un usuario no pudiera.
    """

    __tablename__ = "clave_api"
    __table_args__ = (
        Index("ix_desarrolladores_clave_prefijo", "prefijo", unique=True),
        {"schema": SCHEMA},
    )

    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Los 8 primeros caracteres del secreto. Único global: es la vía de
    #: búsqueda antes de saber a qué organización pertenece la petición.
    prefijo: Mapped[str] = mapped_column(String(16), nullable=False)
    clave_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ambitos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Opcional. Una clave que caduca sola es mejor que una que nadie revisa.
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Para poder detectar las que ya nadie usa y retirarlas.
    ultimo_uso_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SuscripcionWebhook(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """A dónde avisar cuando pase algo, para sistemas de fuera.

    Los eventos son los MISMOS del catálogo que usan las notificaciones
    (`app/core/eventos.py`): es el mismo hecho contado a otro público.

    El secreto se guarda en claro a propósito, al revés que la clave de API:
    hace falta para FIRMAR cada envío, y una firma no se puede calcular con un
    hash del secreto. Es el mismo compromiso que hace Stripe o GitHub.
    """

    __tablename__ = "suscripcion_webhook"
    __table_args__ = (
        Index("ix_desarrolladores_webhook_org", "organization_id", "activa"),
        {"schema": SCHEMA},
    )

    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Códigos del catálogo. Vacío = ninguno; no se interpreta como «todos»,
    #: que sería justo lo contrario de lo que parece al dejarlo en blanco.
    eventos: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    secreto: Mapped[str] = mapped_column(String(64), nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    entregas: Mapped[list["EntregaWebhook"]] = relationship(
        back_populates="suscripcion", cascade="all, delete-orphan"
    )


class EntregaWebhook(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Un intento de avisar, con su resultado.

    Se guarda cada entrega y no solo las fallidas: cuando una integración dice
    «no me ha llegado nada», la única forma de saber quién tiene razón es
    poder enseñar qué se mandó, cuándo y qué contestaron.
    """

    __tablename__ = "entrega_webhook"
    __table_args__ = (
        # Por aquí busca el repartidor: lo pendiente que ya toca reintentar.
        Index("ix_desarrolladores_entrega_pendiente", "estado", "proximo_intento_en"),
        {"schema": SCHEMA},
    )

    suscripcion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.suscripcion_webhook.id", ondelete="CASCADE"),
        nullable=False,
    )
    evento: Mapped[str] = mapped_column(String(64), nullable=False)
    #: El cuerpo exacto que se manda. Se guarda ya montado para que un
    #: reintento mande LO MISMO: recalcularlo días después daría otra cosa.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    estado: Mapped[EstadoEntrega] = mapped_column(
        enum_column(EstadoEntrega, "estado_entrega"),
        nullable=False,
        default=EstadoEntrega.PENDIENTE,
    )
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proximo_intento_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    entregada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    respuesta_codigo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Recortado: el cuerpo de error de un servidor ajeno puede ser enorme y
    #: aquí solo interesa lo suficiente para entender qué pasó.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    suscripcion: Mapped[SuscripcionWebhook] = relationship(back_populates="entregas")
