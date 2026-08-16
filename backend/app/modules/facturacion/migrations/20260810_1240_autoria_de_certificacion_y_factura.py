"""facturacion: creado_por_subject/nombre en certificacion y factura (Fase 12)

Revision ID: facturacion_0002
Revises: facturacion_0001
Create Date: 2026-08-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "facturacion_0002"
down_revision: str | None = "facturacion_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for tabla in ("certificacion", "factura"):
        op.add_column(
            tabla,
            sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
            schema="facturacion",
        )
        op.add_column(
            tabla,
            sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
            schema="facturacion",
        )


def downgrade() -> None:
    for tabla in ("certificacion", "factura"):
        op.drop_column(tabla, "creado_por_nombre", schema="facturacion")
        op.drop_column(tabla, "creado_por_subject", schema="facturacion")
