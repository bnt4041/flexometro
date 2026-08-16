"""ia: creado_por_subject/nombre en sugerencia_patron y lectura_plano (Fase 12)

Revision ID: ia_0003
Revises: ia_0002
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ia_0003"
down_revision: str | None = "ia_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("sugerencia_patron", "lectura_plano"):
        op.add_column(
            tabla,
            sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
            schema="ia",
        )
        op.add_column(
            tabla,
            sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
            schema="ia",
        )


def downgrade() -> None:
    for tabla in ("sugerencia_patron", "lectura_plano"):
        op.drop_column(tabla, "creado_por_nombre", schema="ia")
        op.drop_column(tabla, "creado_por_subject", schema="ia")
