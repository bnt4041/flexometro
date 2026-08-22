"""Plantillas Word para exportar presupuestos con diseño propio.

Escala de `cuenta`, no de `organization`: es un recurso de diseño/ajustes
compartido por todas las organizaciones de la misma cuenta, igual que el
patrón de numeración (ver `numeracion_models.py`) — no un dato de negocio que
deba aislarse por organización. `cuenta_id` nulo marca las plantillas "de
sistema": vienen ya creadas, valen para cualquier cuenta y sirven de patrón de
partida para diseñar una propia.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import AutoriaMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "presupuestos"


class PlantillaPresupuesto(UUIDPrimaryKeyMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "plantilla_docx"
    __table_args__ = {"schema": SCHEMA}

    cuenta_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("core.cuenta.id", ondelete="CASCADE"), nullable=True
    )
    es_sistema: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    archivo_docx_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    # Variables Jinja que `docxtpl` detectó al subir el archivo — para que el
    # admin vea, sin abrir Word, si el diseño reconoce las claves esperadas.
    claves_detectadas: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
