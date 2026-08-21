"""Historial de cambios (Fase 38): quién ha creado, modificado o borrado cada
registro de negocio y qué campos ha cambiado.

Genérico a propósito: una única tabla para todos los módulos, en vez de una
tabla de historial por entidad. La rellena `app.core.auditoria` (un listener
de sesión de SQLAlchemy, no llamadas explícitas desde cada servicio) — así
ningún módulo nuevo se puede "olvidar" de auditar sus cambios, es automático
para cualquier modelo con `AutoriaMixin`.

Lleva RLS igual que las tablas de negocio (a diferencia de `billing_models`,
que es solo para superadmin): cualquier usuario con permiso para ver un
registro puede ver su historial.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import Base, UUIDPrimaryKeyMixin

SCHEMA = "core"


class AccionAuditoria(StrEnum):
    CREADO = "creado"
    MODIFICADO = "modificado"
    ELIMINADO = "eliminado"


class RegistroAuditoria(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "registro_auditoria"
    __table_args__ = (
        # La consulta real siempre es "el historial de ESTE registro
        # concreto" (tabla + registro_id), de ahí el índice compuesto;
        # `organization_id` es solo para la política RLS.
        Index("ix_core_registro_auditoria_registro", "tabla", "registro_id"),
        {"schema": SCHEMA},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "schema.tabla" (p.ej. "terceros.tercero"), calculado por
    # `app.core.auditoria.tabla_de()` — nunca a mano, para que no pueda
    # desincronizarse del nombre real de la tabla.
    tabla: Mapped[str] = mapped_column(String(80), nullable=False)
    registro_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    accion: Mapped[AccionAuditoria] = mapped_column(
        enum_column(AccionAuditoria, "accion_auditoria"), nullable=False
    )
    # Lista de {"campo", "antes", "despues"}; None en creado/eliminado (el
    # propio `accion` ya lo dice, no hace falta listar todas las columnas).
    cambios: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Igual que `UsoIA.usuario_subject`: el usuario vive en Keycloak, no aquí.
    usuario_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    usuario_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
