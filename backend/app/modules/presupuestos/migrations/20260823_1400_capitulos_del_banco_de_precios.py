"""capitulos del banco de precios

Revision ID: presupuestos_0011
Revises: presupuestos_0010
Create Date: 2026-08-23 14:00:00

Fase 50: el banco de precios pasa a organizarse en árbol, como un
presupuesto. `capitulo_banco` es la estructura (dónde está la ficha) y
`familia` sigue siendo la clasificación (qué es la ficha) — dos cosas
distintas a propósito.

RLS de tipo maestro, igual que `concepto` y `familia`: si la cuenta comparte
maestros entre sus empresas, un concepto visible desde la empresa hermana
tiene que poder enseñar el capítulo en el que vive, o la rejilla lo pintaría
huérfano.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls_maestro

revision: str = 'presupuestos_0011'
down_revision: str | None = 'presupuestos_0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'capitulo_banco',
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('codigo', sa.String(length=32), nullable=False),
        sa.Column('resumen', sa.String(length=250), nullable=False),
        sa.Column('texto', sa.Text(), nullable=True),
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('creado_por_subject', sa.String(length=120), nullable=True),
        sa.Column('creado_por_nombre', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ['parent_id'],
            ['presupuestos.capitulo_banco.id'],
            name=op.f('fk_capitulo_banco_parent_id_capitulo_banco'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            ['core.organization.id'],
            name=op.f('fk_capitulo_banco_organization_id_organization'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_capitulo_banco')),
        sa.UniqueConstraint('organization_id', 'codigo', name='capitulo_banco_codigo_unique'),
        schema='presupuestos',
    )
    op.create_index(
        'ix_presupuestos_capitulo_banco_padre',
        'capitulo_banco',
        ['organization_id', 'parent_id'],
        unique=False,
        schema='presupuestos',
    )
    op.create_index(
        op.f('ix_presupuestos_capitulo_banco_parent_id'),
        'capitulo_banco',
        ['parent_id'],
        unique=False,
        schema='presupuestos',
    )
    op.create_index(
        op.f('ix_presupuestos_capitulo_banco_organization_id'),
        'capitulo_banco',
        ['organization_id'],
        unique=False,
        schema='presupuestos',
    )
    op.alter_column('capitulo_banco', 'orden', server_default=None, schema='presupuestos')

    activar_rls_maestro('presupuestos', 'capitulo_banco')

    op.add_column(
        'concepto', sa.Column('capitulo_id', sa.UUID(), nullable=True), schema='presupuestos'
    )
    op.create_index(
        op.f('ix_presupuestos_concepto_capitulo_id'),
        'concepto',
        ['capitulo_id'],
        unique=False,
        schema='presupuestos',
    )
    op.create_foreign_key(
        op.f('fk_concepto_capitulo_id_capitulo_banco'),
        'concepto',
        'capitulo_banco',
        ['capitulo_id'],
        ['id'],
        source_schema='presupuestos',
        referent_schema='presupuestos',
        ondelete='SET NULL',
    )
    # server_default en el ALTER para rellenar las filas que ya existen, y se
    # retira después: el valor lo pone el ORM en las altas nuevas.
    op.add_column(
        'concepto',
        sa.Column('orden', sa.Integer(), nullable=False, server_default='0'),
        schema='presupuestos',
    )
    op.alter_column('concepto', 'orden', server_default=None, schema='presupuestos')


def downgrade() -> None:
    op.drop_column('concepto', 'orden', schema='presupuestos')
    op.drop_constraint(
        op.f('fk_concepto_capitulo_id_capitulo_banco'),
        'concepto',
        schema='presupuestos',
        type_='foreignkey',
    )
    op.drop_column('concepto', 'capitulo_id', schema='presupuestos')
    op.drop_table('capitulo_banco', schema='presupuestos')
