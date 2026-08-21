"""creditos ia en tarifa

Revision ID: f4a1c9e2b3d7
Revises: 260c71294d89
Create Date: 2026-08-21 11:00:00

Fase 38: "créditos IA", una unidad propia de consumo de IA por cuenta que no
obliga al usuario final a entender tokens de DeepSeek/Gemini por separado —
ver `app/modules/core/creditos_service.py`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f4a1c9e2b3d7'
down_revision: str | None = '260c71294d89'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'tarifa',
        sa.Column('valor_credito_euros', sa.Numeric(10, 6), nullable=False, server_default='0.001000'),
        schema='core',
    )
    op.add_column(
        'tarifa',
        sa.Column('creditos_ia_incluidos_mes', sa.Integer(), nullable=False, server_default='0'),
        schema='core',
    )
    op.alter_column('tarifa', 'valor_credito_euros', server_default=None, schema='core')
    op.alter_column('tarifa', 'creditos_ia_incluidos_mes', server_default=None, schema='core')


def downgrade() -> None:
    op.drop_column('tarifa', 'creditos_ia_incluidos_mes', schema='core')
    op.drop_column('tarifa', 'valor_credito_euros', schema='core')
