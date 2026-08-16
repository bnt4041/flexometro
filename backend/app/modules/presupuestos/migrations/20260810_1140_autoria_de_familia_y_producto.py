"""catalogo: creado_por_subject/nombre en familia y producto (Fase 12)

Revision ID: catalogo_0002
Revises: catalogo_0001
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "catalogo_0002"
down_revision: str | None = "catalogo_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("familia", "producto"):
        op.add_column(
            tabla,
            sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
            schema="catalogo",
        )
        op.add_column(
            tabla,
            sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
            schema="catalogo",
        )


def downgrade() -> None:
    for tabla in ("familia", "producto"):
        op.drop_column(tabla, "creado_por_nombre", schema="catalogo")
        op.drop_column(tabla, "creado_por_subject", schema="catalogo")
