"""informes: informes guardados

Solo se guarda la definición, nunca el resultado: un informe tiene que
enseñar los datos de hoy, y cachear filas haría que dos personas con permisos
distintos vieran el mismo número.

Revision ID: inf_0001
Revises:
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import (
    activar_rls,
    conceder_privilegios_app,
    desactivar_rls,
    revocar_privilegios_app,
)

revision: str = "inf_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("informes",)
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "informes"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "informe",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("fuente", sa.String(length=64), nullable=False),
        sa.Column(
            "dimensiones", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "metricas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "filtros", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("grafico", sa.String(length=20), nullable=False, server_default="tabla"),
        sa.Column("compartido", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_informe_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_informe")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_informes_informe_organization_id"), "informe", ["organization_id"], schema=SCHEMA
    )
    conceder_privilegios_app(SCHEMA)
    activar_rls(SCHEMA, "informe")


def downgrade() -> None:
    desactivar_rls(SCHEMA, "informe")
    revocar_privilegios_app(SCHEMA)
    op.drop_table("informe", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
