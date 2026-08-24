"""cuentas bancarias de terceros

Revision ID: terceros_0004
Revises: terceros_0003
Create Date: 2026-08-23 12:00:00

Fase 47: los IBAN que un tercero (cliente o proveedor) nos ha dado —
distinto de `core.cuenta_financiera` (Fase 44), que son las cuentas PROPIAS
de la empresa. Maestro compartido desde que nace, igual que `contacto`: si
el tercero es el mismo en las dos empresas de la cuenta, sus cuentas
bancarias también lo son.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls_maestro

revision: str = 'terceros_0004'
down_revision: str | None = 'terceros_0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'cuenta_bancaria',
        sa.Column('tercero_id', sa.UUID(), nullable=False),
        sa.Column('titular', sa.String(length=200), nullable=True),
        sa.Column('iban', sa.String(length=34), nullable=False),
        sa.Column('bic', sa.String(length=11), nullable=True),
        sa.Column('es_principal', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('creado_por_subject', sa.String(length=120), nullable=True),
        sa.Column('creado_por_nombre', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ['tercero_id'],
            ['terceros.tercero.id'],
            name=op.f('fk_cuenta_bancaria_tercero_id_tercero'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['core.organization.id'],
            name=op.f('fk_cuenta_bancaria_organization_id_organization'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cuenta_bancaria')),
        schema='terceros',
    )
    op.create_index(
        'ix_terceros_cuenta_bancaria_tercero',
        'cuenta_bancaria',
        ['tercero_id'],
        unique=False,
        schema='terceros',
    )
    op.create_index(
        op.f('ix_terceros_cuenta_bancaria_organization_id'),
        'cuenta_bancaria',
        ['organization_id'],
        unique=False,
        schema='terceros',
    )
    op.alter_column('cuenta_bancaria', 'es_principal', server_default=None, schema='terceros')
    op.alter_column('cuenta_bancaria', 'activo', server_default=None, schema='terceros')

    activar_rls_maestro('terceros', 'cuenta_bancaria')


def downgrade() -> None:
    op.drop_table('cuenta_bancaria', schema='terceros')
