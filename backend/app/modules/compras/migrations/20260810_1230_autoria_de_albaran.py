"""compras: creado_por_subject/nombre en albaran (Fase 12)

Revision ID: compras_0002
Revises: compras_0001
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "compras_0002"
down_revision: str | None = "compras_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "albaran",
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        schema="compras",
    )
    op.add_column(
        "albaran",
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        schema="compras",
    )


def downgrade() -> None:
    op.drop_column("albaran", "creado_por_nombre", schema="compras")
    op.drop_column("albaran", "creado_por_subject", schema="compras")
