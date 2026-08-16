"""obras: creado_por_subject/nombre en obra y personal (Fase 12)

Revision ID: obras_0002
Revises: obras_0001
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "obras_0002"
down_revision: str | None = "obras_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("obra", "personal"):
        op.add_column(
            tabla,
            sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
            schema="obras",
        )
        op.add_column(
            tabla,
            sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
            schema="obras",
        )


def downgrade() -> None:
    for tabla in ("obra", "personal"):
        op.drop_column(tabla, "creado_por_nombre", schema="obras")
        op.drop_column(tabla, "creado_por_subject", schema="obras")
