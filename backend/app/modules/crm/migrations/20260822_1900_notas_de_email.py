"""notas de email

Revision ID: crm_0002
Revises: crm_0001
Create Date: 2026-08-22 19:00:00

Fase 42: enviar un correo desde la pestaña CRM de cualquier ficha y dejarlo
registrado como una nota más, distinguible de una nota de texto libre.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'crm_0002'
down_revision: str | None = 'crm_0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'nota',
        sa.Column(
            'tipo',
            sa.Enum('texto', 'email', name='tipo_nota', native_enum=False, length=32),
            nullable=False,
            server_default='texto',
        ),
        schema='crm',
    )
    op.alter_column('nota', 'tipo', server_default=None, schema='crm')
    op.add_column('nota', sa.Column('asunto', sa.String(length=255), nullable=True), schema='crm')
    op.add_column('nota', sa.Column('destinatario', sa.String(length=255), nullable=True), schema='crm')
    op.add_column(
        'nota',
        sa.Column('adjuntos', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        schema='crm',
    )
    op.alter_column('nota', 'adjuntos', server_default=None, schema='crm')


def downgrade() -> None:
    op.drop_column('nota', 'adjuntos', schema='crm')
    op.drop_column('nota', 'destinatario', schema='crm')
    op.drop_column('nota', 'asunto', schema='crm')
    op.drop_column('nota', 'tipo', schema='crm')
