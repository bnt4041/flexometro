"""planos: el dibujo vectorial de un DXF

Revision ID: pln_0002
Revises: pln_0001
Create Date: 2026-08-31
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "pln_0002"
down_revision: str | None = "pln_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "planos"


def upgrade() -> None:
    # JSONB y no una tabla de entidades: los trazos de una hoja se leen
    # siempre enteros y a la vez —son el dibujo— así que partirlos en miles de
    # filas solo añadiría una consulta pesada para volver a juntarlos.
    op.add_column(
        "hoja_plano",
        sa.Column("dibujo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("hoja_plano", "dibujo", schema=SCHEMA)
