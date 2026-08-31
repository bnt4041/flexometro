"""core: favoritos por usuario

Páginas que cada uno quiere tener a mano en su menú.

En base de datos y no en el navegador: en una obra se entra desde la oficina,
desde el portátil y desde el móvil, y unos favoritos que solo viven en un
equipo son un cajón que hay que volver a llenar en cada sitio.

Revision ID: core_favoritos_0001
Revises: core_permisos_0001
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.rls import activar_rls, desactivar_rls

revision: str = "core_favoritos_0001"
down_revision: str | None = "core_permisos_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favorito",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("usuario_subject", sa.String(length=120), nullable=False),
        sa.Column("etiqueta", sa.String(length=120), nullable=False),
        sa.Column("ruta", sa.String(length=400), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_favorito_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_favorito")),
        sa.UniqueConstraint(
            "organization_id", "usuario_subject", "ruta", name="favorito_unique"
        ),
        schema="core",
    )
    op.create_index(
        op.f("ix_core_favorito_organization_id"), "favorito", ["organization_id"], schema="core"
    )
    op.create_index(
        "ix_core_favorito_usuario", "favorito",
        ["organization_id", "usuario_subject"], schema="core",
    )
    activar_rls("core", "favorito")


def downgrade() -> None:
    desactivar_rls("core", "favorito")
    op.drop_table("favorito", schema="core")
