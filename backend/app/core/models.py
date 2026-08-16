"""Base declarativa y mixins compartidos por todos los módulos.

`OrganizationMixin` es obligatorio en toda tabla raíz de negocio: el despliegue
inicial es single-tenant, pero el modelo de datos es multi-tenant desde el
primer día. En Fase 5 esta misma columna es la que sostendrá las políticas RLS
de PostgreSQL sin migrar datos.

Cada módulo posee un schema propio de PostgreSQL (`core`, `presupuestos`,
`obras`...), declarado en `__table_args__`. Es lo que hace que el espacio de
datos de un módulo sea realmente suyo y que su migración pueda crearlo o
borrarlo sin tocar a los demás.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Convención de nombres explícita: sin ella Alembic genera constraints anónimas
# que luego no se pueden alterar por nombre en una migración.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # `updated_at` se calcula en el servidor (onupdate=now()), así que tras un
    # UPDATE la columna queda expirada. Leerla luego —al serializar la
    # respuesta, por ejemplo— dispararía una carga perezosa fuera del contexto
    # greenlet y revienta con MissingGreenlet. Con eager_defaults, SQLAlchemy
    # añade RETURNING y trae el valor en la misma sentencia.
    __mapper_args__ = {"eager_defaults": True}


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrganizationMixin:
    """Toda tabla raíz de negocio lleva organization_id desde el día uno."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class AutoriaMixin:
    """Quién creó el registro, para el permiso "solo los míos" (Fase 12).

    Solo lo llevan las entidades raíz de cada módulo (un presupuesto, una
    obra, un tercero...) — las de línea (una partida, un cobro, una línea de
    medición) heredan la visibilidad de su padre y no necesitan su propia
    autoría. Nullable a propósito: los registros de antes de esta fase no
    tienen quién los creó y no se puede inventar; para ellos, "solo los
    míos" simplemente no los verá nadie (ver `permisos.py`), que es el
    comportamiento correcto y no un error.

    No es una FK a ningún sitio: el usuario vive en Keycloak, no en esta base
    de datos, igual que `UsoIA.usuario_subject`.
    """

    creado_por_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    creado_por_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
