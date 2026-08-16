"""Overrides de traducción por cuenta — Fase 19.

Los textos base de la interfaz viven en el propio frontend (`frontend/src/
i18n/es.ts`), organizados por clave (`modulo.pantalla.campo`). Esta tabla
solo guarda las claves que una cuenta ha decidido reescribir a su gusto
(p.ej. "obra" → "proyecto") — no un catálogo de idiomas, un idioma nuevo de
verdad sigue siendo trabajo de traducir el bundle base, no de esta tabla.
"""

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class TraduccionOverride(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "traduccion_override"
    __table_args__ = (
        UniqueConstraint("cuenta_id", "clave", name="traduccion_override_unique"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.cuenta.id", ondelete="CASCADE"), nullable=False
    )
    clave: Mapped[str] = mapped_column(String(200), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
