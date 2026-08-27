"""CRM (Fase 29): notas de seguimiento sobre cualquier objeto grande del
negocio (tercero, presupuesto, obra, certificación, factura) — un cuaderno de
bitácora compartido por el equipo, sin más estructura que "quién escribió
qué y cuándo".

Mismo patrón `entidad`/`entidad_id` sin FK real que `campos_libres.valor` y
`terceros.contacto_asociado`: una nota no necesita acoplar este módulo a
cinco módulos de negocio distintos para algo que RLS ya protege.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "crm"


class EntidadNota(StrEnum):
    TERCERO = "tercero"
    CONTACTO = "contacto"
    PRESUPUESTO = "presupuesto"
    OBRA = "obra"
    CERTIFICACION = "certificacion"
    FACTURA = "factura"
    PEDIDO = "pedido"
    CONTRATO = "contrato"
    ALBARAN = "albaran"
    FACTURA_RECIBIDA = "factura_recibida"


class TipoNota(StrEnum):
    TEXTO = "texto"
    EMAIL = "email"


class Nota(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "nota"
    __table_args__ = (
        Index("ix_crm_nota_entidad", "organization_id", "entidad", "entidad_id"),
        {"schema": SCHEMA},
    )

    entidad: Mapped[EntidadNota] = mapped_column(enum_column(EntidadNota, "entidad_nota"), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    # Fase 42: una nota puede ser el registro de un correo enviado desde esta
    # misma ficha, no solo texto libre — `asunto`/`destinatario` y qué
    # documentos se adjuntaron quedan aparte de `contenido` (que guarda el
    # cuerpo) para poder mostrarlos en la línea de tiempo sin parsear nada.
    tipo: Mapped[TipoNota] = mapped_column(enum_column(TipoNota, "tipo_nota"), nullable=False, default=TipoNota.TEXTO)
    asunto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destinatario: Mapped[str | None] = mapped_column(String(255), nullable=True)
    adjuntos: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
