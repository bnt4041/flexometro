"""terceros: creado_por_subject/nombre en tercero y contacto (Fase 12)

Revision ID: terceros_0002
Revises: terceros_0001
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "terceros_0002"
down_revision: str | None = "terceros_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("tercero", "contacto"):
        op.add_column(
            tabla,
            sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
            schema="terceros",
        )
        op.add_column(
            tabla,
            sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
            schema="terceros",
        )


def downgrade() -> None:
    for tabla in ("tercero", "contacto"):
        op.drop_column(tabla, "creado_por_nombre", schema="terceros")
        op.drop_column(tabla, "creado_por_subject", schema="terceros")
