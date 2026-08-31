"""Gestor documental (Fase 30): ficheros subidos por el usuario y asociados a
cualquier objeto grande del negocio (tercero, presupuesto, obra,
certificación, factura). El contenido no vive en Postgres — solo el
`object_key` que apunta al objeto real en MinIO (ver `app/core/storage.py`);
esta tabla es el índice, no el almacén.

Mismo patrón `entidad`/`entidad_id` sin FK real que `crm.Nota` y
`terceros.contacto_asociado`.
"""

import uuid
from enum import StrEnum

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import (
    AutoriaMixin,
    Base,
    OrganizationMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

SCHEMA = "documentos"


class EntidadDocumento(StrEnum):
    TERCERO = "tercero"
    CONTACTO = "contacto"
    CONCEPTO = "concepto"
    PRESUPUESTO = "presupuesto"
    OBRA = "obra"
    CERTIFICACION = "certificacion"
    FACTURA = "factura"
    SOLICITUD_PRECIOS = "solicitud_precios"
    PEDIDO = "pedido"
    CONTRATO = "contrato"
    ALBARAN = "albaran"
    FACTURA_RECIBIDA = "factura_recibida"
    # Módulo PRL. `PERSONAL` y `RECURSO` cuelgan de la ficha correspondiente;
    # `PRL_EMPRESA` es para los papeles de la organización entera, que no
    # tienen ficha propia a la que colgarse.
    PERSONAL = "personal"
    RECURSO = "recurso"
    PRL_EMPRESA = "prl_empresa"
    SOLICITUD_FIRMA = "solicitud_firma"


class Documento(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "documento"
    __table_args__ = (
        Index("ix_documentos_documento_entidad", "organization_id", "entidad", "entidad_id"),
        {"schema": SCHEMA},
    )

    entidad: Mapped[EntidadDocumento] = mapped_column(
        enum_column(EntidadDocumento, "entidad_documento"), nullable=False
    )
    entidad_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Ruta dentro del bucket — incluye organization_id para que dos
    # organizaciones nunca puedan colisionar en la misma key aunque suban un
    # fichero con el mismo nombre el mismo segundo.
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
