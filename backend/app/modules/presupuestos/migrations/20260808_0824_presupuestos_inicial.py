"""presupuestos: conceptos y descomposición

Rama propia encadenada tras catalogo: concepto.producto_id apunta a
catalogo.producto, y sin `depends_on` el orden entre ramas no está garantizado.

Revision ID: presupuestos_0001
Revises:
Create Date: 2026-08-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "presupuestos_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("presupuestos",)
depends_on: str | Sequence[str] | None = ("catalogo",)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS presupuestos")

    op.create_table('concepto',
    sa.Column('codigo', sa.String(length=32), nullable=False),
    sa.Column('tipo', sa.Enum('basico', 'auxiliar', 'unitario', name='tipo_concepto', native_enum=False, length=32), nullable=False),
    sa.Column('naturaleza', sa.Enum('sin_clasificar', 'mano_obra', 'maquinaria', 'material', 'residuo', 'otro', name='naturaleza_concepto', native_enum=False, length=32), nullable=False),
    sa.Column('unidad', sa.String(length=10), nullable=False),
    sa.Column('resumen', sa.String(length=250), nullable=False),
    sa.Column('texto', sa.Text(), nullable=True),
    sa.Column('precio', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('origen_precio', sa.Enum('manual', 'producto', 'descomposicion', name='origen_precio', native_enum=False, length=32), nullable=False),
    sa.Column('fecha_precio', sa.Date(), nullable=True),
    sa.Column('producto_id', sa.UUID(), nullable=True),
    sa.Column('costes_indirectos', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('origen_dato', sa.Enum('manual', 'fiebdc3', 'ia', 'importado', name='origen_dato', native_enum=False, length=32), nullable=False),
    sa.Column('atributos', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_concepto_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['producto_id'], ['catalogo.producto.id'], name=op.f('fk_concepto_producto_id_producto'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_concepto')),
    sa.UniqueConstraint('organization_id', 'codigo', name='concepto_codigo_unique'),
    schema='presupuestos'
    )
    op.create_index(op.f('ix_presupuestos_concepto_organization_id'), 'concepto', ['organization_id'], unique=False, schema='presupuestos')
    op.create_index(op.f('ix_presupuestos_concepto_producto_id'), 'concepto', ['producto_id'], unique=False, schema='presupuestos')
    op.create_index('ix_presupuestos_concepto_resumen', 'concepto', ['organization_id', 'resumen'], unique=False, schema='presupuestos')
    op.create_index('ix_presupuestos_concepto_tipo', 'concepto', ['organization_id', 'tipo'], unique=False, schema='presupuestos')
    op.create_table('descomposicion',
    sa.Column('padre_id', sa.UUID(), nullable=False),
    sa.Column('hijo_id', sa.UUID(), nullable=False),
    sa.Column('rendimiento', sa.Numeric(precision=14, scale=6), nullable=False),
    sa.Column('factor', sa.Numeric(precision=14, scale=6), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['hijo_id'], ['presupuestos.concepto.id'], name=op.f('fk_descomposicion_hijo_id_concepto'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_descomposicion_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['padre_id'], ['presupuestos.concepto.id'], name=op.f('fk_descomposicion_padre_id_concepto'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_descomposicion')),
    schema='presupuestos'
    )
    op.create_index('ix_presupuestos_descomposicion_hijo', 'descomposicion', ['hijo_id'], unique=False, schema='presupuestos')
    op.create_index(op.f('ix_presupuestos_descomposicion_organization_id'), 'descomposicion', ['organization_id'], unique=False, schema='presupuestos')
    op.create_index('ix_presupuestos_descomposicion_padre', 'descomposicion', ['padre_id'], unique=False, schema='presupuestos')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_presupuestos_descomposicion_padre', table_name='descomposicion', schema='presupuestos')
    op.drop_index(op.f('ix_presupuestos_descomposicion_organization_id'), table_name='descomposicion', schema='presupuestos')
    op.drop_index('ix_presupuestos_descomposicion_hijo', table_name='descomposicion', schema='presupuestos')
    op.drop_table('descomposicion', schema='presupuestos')
    op.drop_index('ix_presupuestos_concepto_tipo', table_name='concepto', schema='presupuestos')
    op.drop_index('ix_presupuestos_concepto_resumen', table_name='concepto', schema='presupuestos')
    op.drop_index(op.f('ix_presupuestos_concepto_producto_id'), table_name='concepto', schema='presupuestos')
    op.drop_index(op.f('ix_presupuestos_concepto_organization_id'), table_name='concepto', schema='presupuestos')
    op.drop_table('concepto', schema='presupuestos')
    op.execute("DROP SCHEMA IF EXISTS presupuestos CASCADE")
