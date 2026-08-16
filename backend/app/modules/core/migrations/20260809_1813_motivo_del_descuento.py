"""motivo del descuento

Revision ID: 9f859daaf6cb
Revises: c7eb41f58eec
Create Date: 2026-08-09 18:13:29.885512
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9f859daaf6cb'
down_revision: str | None = 'c7eb41f58eec'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default temporal: ya hay descuentos creados (Fase 11) antes de
    # que existiera esta columna; se retira en cuanto la columna está
    # poblada, para que el valor por defecto real siga viviendo solo en el
    # modelo de Python, no duplicado aquí.
    op.add_column(
        'descuento',
        sa.Column(
            'motivo',
            sa.Enum(
                'primer_mes_gratis', 'fidelizacion', 'retencion', 'campana',
                'aumento_modulos', 'otro',
                name='motivo_descuento', native_enum=False, length=32,
            ),
            nullable=False,
            server_default='otro',
        ),
        schema='core',
    )
    op.alter_column('descuento', 'motivo', server_default=None, schema='core')


def downgrade() -> None:
    op.drop_column('descuento', 'motivo', schema='core')
