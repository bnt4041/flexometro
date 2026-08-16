"""Grupos y permisos por módulo (Fase 12).

Un grupo pertenece a una organización y reúne usuarios de Keycloak (por
`subject`, igual que `UsoIA` — el usuario vive en Keycloak, no aquí) con un
permiso por módulo: qué puede VER (nada / lo suyo / todo) y qué puede EDITAR
(nada / lo suyo / todo). "Lo suyo" se resuelve contra `AutoriaMixin`
(`creado_por_subject`) de cada entidad raíz — ver `app/core/permisos.py`.

Estas tres tablas SÍ llevan RLS: a diferencia de `Tarifa`/`Descuento`
(exclusivas del superadmin), los grupos también los gestiona el propio
tenant (rol `admin` de su organización) desde una pantalla normal, igual que
`organization_module` — ese es el criterio que decide si una tabla nueva
lleva RLS o no en este proyecto, no si "sale del schema core".
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Alcance, enum_column
from app.core.models import Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class Grupo(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    __tablename__ = "grupo"
    __table_args__ = (
        UniqueConstraint("organization_id", "nombre", name="grupo_nombre_unique"),
        {"schema": SCHEMA},
    )

    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(250), nullable=True)

    permisos: Mapped[list["GrupoPermiso"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan"
    )
    miembros: Mapped[list["GrupoUsuario"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan"
    )


class GrupoPermiso(UUIDPrimaryKeyMixin, OrganizationMixin, Base):
    """Un módulo, dos alcances. `module_code` no es FK: los módulos viven en
    el registro de código (`app.core.modules.registry`), no en base de datos
    — mismo motivo que `OrganizationModule.module_code`."""

    __tablename__ = "grupo_permiso"
    __table_args__ = (
        UniqueConstraint("grupo_id", "module_code", name="grupo_permiso_unique"),
        {"schema": SCHEMA},
    )

    grupo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.grupo.id", ondelete="CASCADE"), nullable=False
    )
    module_code: Mapped[str] = mapped_column(String(64), nullable=False)
    ver: Mapped[Alcance] = mapped_column(
        enum_column(Alcance, "alcance_ver"), nullable=False, default=Alcance.NINGUNO
    )
    editar: Mapped[Alcance] = mapped_column(
        enum_column(Alcance, "alcance_editar"), nullable=False, default=Alcance.NINGUNO
    )

    grupo: Mapped[Grupo] = relationship(back_populates="permisos")


class GrupoUsuario(UUIDPrimaryKeyMixin, OrganizationMixin, Base):
    """Quién pertenece al grupo. `usuario_subject` es el `sub` del token de
    Keycloak — no hay tabla de usuarios propia, igual que en `UsoIA`."""

    __tablename__ = "grupo_usuario"
    __table_args__ = (
        UniqueConstraint("grupo_id", "usuario_subject", name="grupo_usuario_unique"),
        Index("ix_core_grupo_usuario_subject", "organization_id", "usuario_subject"),
        {"schema": SCHEMA},
    )

    grupo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.grupo.id", ondelete="CASCADE"), nullable=False
    )
    usuario_subject: Mapped[str] = mapped_column(String(120), nullable=False)
    usuario_nombre: Mapped[str] = mapped_column(String(200), nullable=False)

    grupo: Mapped[Grupo] = relationship(back_populates="miembros")
