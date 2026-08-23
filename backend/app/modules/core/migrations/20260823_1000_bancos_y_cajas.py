"""bancos y cajas

Revision ID: a71d4b6e5c90
Revises: f69c3a8e1d52
Create Date: 2026-08-23 10:00:00

Fase 44: dónde está el dinero de cada empresa — cuentas bancarias y cajas de
efectivo. Por `organization_id` con RLS, no por cuenta: el dinero de una
sociedad no es el de la otra, y un cobro (que ya es de una organización
concreta) no debe poder apuntar a la cuenta de la empresa de al lado.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls

revision: str = 'a71d4b6e5c90'
down_revision: str | None = 'f69c3a8e1d52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'cuenta_financiera',
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column(
            'tipo',
            sa.Enum('banco', 'caja', name='tipo_cuenta_financiera', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column('banco', sa.String(length=120), nullable=True),
        sa.Column('iban', sa.String(length=34), nullable=True),
        sa.Column('bic', sa.String(length=11), nullable=True),
        sa.Column('es_predeterminada', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('activa', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('creado_por_subject', sa.String(length=120), nullable=True),
        sa.Column('creado_por_nombre', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['core.organization.id'],
            name=op.f('fk_cuenta_financiera_organization_id_organization'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cuenta_financiera')),
        sa.UniqueConstraint('organization_id', 'nombre', name='cuenta_financiera_nombre_unique'),
        schema='core',
    )
    op.create_index(
        'ix_core_cuenta_financiera_org',
        'cuenta_financiera',
        ['organization_id', 'activa'],
        unique=False,
        schema='core',
    )
    op.create_index(
        op.f('ix_core_cuenta_financiera_organization_id'),
        'cuenta_financiera',
        ['organization_id'],
        unique=False,
        schema='core',
    )
    op.alter_column('cuenta_financiera', 'es_predeterminada', server_default=None, schema='core')
    op.alter_column('cuenta_financiera', 'activa', server_default=None, schema='core')

    activar_rls('core', 'cuenta_financiera')


def downgrade() -> None:
    op.drop_table('cuenta_financiera', schema='core')
