"""limite de empresas por cuenta

Revision ID: c2f5e8d03b12
Revises: b1e4d7c92a01
Create Date: 2026-08-22 15:00:00

Fase 41: cuántas organizaciones (empresas/CIFs) puede tener una cuenta.
Autoservicio libre desde Ajustes -> Empresas, no atado a la tarifa — el
propio admin de organización lo sube o lo baja. Por defecto 2.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c2f5e8d03b12'
down_revision: str | None = 'b1e4d7c92a01'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'cuenta',
        sa.Column('max_organizaciones', sa.Integer(), nullable=False, server_default='2'),
        schema='core',
    )
    op.alter_column('cuenta', 'max_organizaciones', server_default=None, schema='core')


def downgrade() -> None:
    op.drop_column('cuenta', 'max_organizaciones', schema='core')
