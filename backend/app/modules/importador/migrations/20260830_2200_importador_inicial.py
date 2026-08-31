"""importador: importaciones desde CSV y Excel

Las filas leídas se guardan en la propia importación para que lo que se
importa sea exactamente lo que se previsualizó.

Revision ID: imp_0001
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

revision: str = "imp_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("importador",)
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "importador"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "importacion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("destino", sa.String(length=64), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "preparada", "completada", "parcial", "fallida",
                name="estado_importacion", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="preparada",
        ),
        sa.Column(
            "columnas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "filas", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "mapeo", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "resultado", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("creadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("con_error", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ejecutada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
            name=op.f("fk_importacion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_importacion")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_importador_importacion_organization_id"),
        "importacion", ["organization_id"], schema=SCHEMA,
    )
    conceder_privilegios_app(SCHEMA)
    activar_rls(SCHEMA, "importacion")


def downgrade() -> None:
    desactivar_rls(SCHEMA, "importacion")
    revocar_privilegios_app(SCHEMA)
    op.drop_table("importacion", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
