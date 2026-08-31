"""Tickets, wiki y el índice que permite al asistente apoyarse en ellos."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
from app.modules.soporte.embeddings import DIMENSIONES
from app.modules.soporte.enums import EstadoTicket, OrigenFragmento, Prioridad, TipoTicket

SCHEMA = "soporte"


class Ticket(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "ticket"
    __table_args__ = (
        Index("ix_soporte_ticket_estado", "organization_id", "estado"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)

    tipo: Mapped[TipoTicket] = mapped_column(
        enum_column(TipoTicket, "tipo_ticket"), nullable=False, default=TipoTicket.PETICION
    )
    estado: Mapped[EstadoTicket] = mapped_column(
        enum_column(EstadoTicket, "estado_ticket"), nullable=False, default=EstadoTicket.NUEVO
    )
    prioridad: Mapped[Prioridad] = mapped_column(
        enum_column(Prioridad, "prioridad_ticket"), nullable=False, default=Prioridad.NORMAL
    )

    #: A quién le toca. Nulo = sin asignar, que es un estado real y no un
    #: error: un ticket recién abierto todavía no es de nadie.
    asignado_a_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    asignado_a_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)

    #: Dónde estaba el usuario al abrirlo. Se guarda porque «no me deja
    #: guardar» sin saber en qué pantalla es una hora de ida y vuelta.
    ruta_origen: Mapped[str | None] = mapped_column(String(400), nullable=True)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mensajes: Mapped[list["MensajeTicket"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", lazy="selectin"
    )


class MensajeTicket(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "mensaje_ticket"
    __table_args__ = ({"schema": SCHEMA},)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.ticket.id", ondelete="CASCADE"), nullable=False
    )
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    #: Nota interna: la ve quien atiende, no quien abrió el ticket.
    interno: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Lo escribió el asistente, no una persona. Se marca para que nadie
    #: confunda una sugerencia automática con una respuesta de soporte.
    de_ia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ticket: Mapped[Ticket] = relationship(back_populates="mensajes")


class PaginaWiki(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Una página de ayuda. Markdown, sin editor rico: el contenido lo escribe
    quien sabe del tema, no un maquetador."""

    __tablename__ = "pagina_wiki"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="pagina_wiki_slug_unique"),
        {"schema": SCHEMA},
    )

    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False, default="")
    categoria: Mapped[str | None] = mapped_column(String(80), nullable=True)
    publicada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Sube en cada guardado. No hay histórico de versiones todavía; esto es
    #: lo que permitirá añadirlo sin migrar nada.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Cuándo se indexó por última vez. Comparado con `updated_at` dice si el
    #: índice está al día sin tener que recalcular nada para saberlo.
    indexada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Fragmento(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Un trozo de texto con su vector, para buscar por significado.

    Va en su propia tabla y no como columna de la página porque una página se
    parte en varios trozos: buscar sobre el vector de una página entera daría
    un resultado difuso que no señala de qué parte habla.
    """

    __tablename__ = "fragmento"
    __table_args__ = (
        Index("ix_soporte_fragmento_origen", "organization_id", "origen", "origen_id"),
        {"schema": SCHEMA},
    )

    origen: Mapped[OrigenFragmento] = mapped_column(
        enum_column(OrigenFragmento, "origen_fragmento"), nullable=False
    )
    origen_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    #: Para poder enseñar de dónde sale una respuesta sin otra consulta.
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONES), nullable=False)
