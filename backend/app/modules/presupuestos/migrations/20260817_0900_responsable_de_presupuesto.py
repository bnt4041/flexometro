"""responsable de presupuesto

Revision ID: presupuestos_0006
Revises: presupuestos_0005
Create Date: 2026-08-17 09:00:00

Fase 31: quién lleva el presupuesto — reasignable en cualquier momento, a
diferencia de `creado_por_subject` (fijado al crear). Mismo patrón
subject+nombre desnormalizado que `AutoriaMixin`, sin FK a Keycloak.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "presupuestos_0006"
down_revision: str | None = "presupuestos_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "presupuesto",
        sa.Column("responsable_subject", sa.String(length=120), nullable=True),
        schema="presupuestos",
    )
    op.add_column(
        "presupuesto",
        sa.Column("responsable_nombre", sa.String(length=200), nullable=True),
        schema="presupuestos",
    )


def downgrade() -> None:
    op.drop_column("presupuesto", "responsable_nombre", schema="presupuestos")
    op.drop_column("presupuesto", "responsable_subject", schema="presupuestos")
