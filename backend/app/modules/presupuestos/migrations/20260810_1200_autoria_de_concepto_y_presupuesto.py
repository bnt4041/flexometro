"""presupuestos: creado_por_subject/nombre en concepto y presupuesto (Fase 12)

Revision ID: presupuestos_0004
Revises: 348ae1ac40fa
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "presupuestos_0004"
down_revision: str | None = "348ae1ac40fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("concepto", "presupuesto"):
        op.add_column(
            tabla,
            sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
            schema="presupuestos",
        )
        op.add_column(
            tabla,
            sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
            schema="presupuestos",
        )


def downgrade() -> None:
    for tabla in ("concepto", "presupuesto"):
        op.drop_column(tabla, "creado_por_nombre", schema="presupuestos")
        op.drop_column(tabla, "creado_por_subject", schema="presupuestos")
