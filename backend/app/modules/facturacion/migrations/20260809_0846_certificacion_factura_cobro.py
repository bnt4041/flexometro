"""facturacion: certificación, factura y cobro

Rama propia encadenada tras obras y terceros: `certificacion.obra_id` y
`factura.obra_id` apuntan a obras.obra, `certificacion_linea.partida_id` a
presupuestos.partida (garantizado transitivamente por la dependencia de
obras) y `factura.cliente_id` a terceros.tercero.

Revision ID: facturacion_0001
Revises:
Create Date: 2026-08-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "facturacion_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("facturacion",)
depends_on: str | Sequence[str] | None = ("obras", "terceros")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS facturacion")

    op.create_table('certificacion',
    sa.Column('codigo', sa.String(length=32), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('obra_id', sa.UUID(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('estado', sa.Enum('borrador', 'emitida', name='estado_certificacion', native_enum=False, length=32), nullable=False),
    sa.Column('retencion_garantia_pct', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['obra_id'], ['obras.obra.id'], name=op.f('fk_certificacion_obra_id_obra'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_certificacion_organization_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_certificacion')),
    sa.UniqueConstraint('obra_id', 'numero', name='certificacion_obra_numero_unique'),
    sa.UniqueConstraint('organization_id', 'codigo', name='certificacion_codigo_unique'),
    schema='facturacion'
    )
    op.create_index('ix_facturacion_certificacion_obra', 'certificacion', ['obra_id'], unique=False, schema='facturacion')
    op.create_index(op.f('ix_facturacion_certificacion_organization_id'), 'certificacion', ['organization_id'], unique=False, schema='facturacion')
    op.create_table('certificacion_linea',
    sa.Column('certificacion_id', sa.UUID(), nullable=False),
    sa.Column('partida_id', sa.UUID(), nullable=False),
    sa.Column('codigo', sa.String(length=32), nullable=False),
    sa.Column('resumen', sa.String(length=250), nullable=False),
    sa.Column('unidad', sa.String(length=10), nullable=False),
    sa.Column('precio', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('medicion_anterior', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('medicion_actual', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('medicion_periodo', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('importe_periodo', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['certificacion_id'], ['facturacion.certificacion.id'], name=op.f('fk_certificacion_linea_certificacion_id_certificacion'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_certificacion_linea_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['partida_id'], ['presupuestos.partida.id'], name=op.f('fk_certificacion_linea_partida_id_partida'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_certificacion_linea')),
    sa.UniqueConstraint('certificacion_id', 'partida_id', name='certificacion_linea_partida_unique'),
    schema='facturacion'
    )
    op.create_index('ix_facturacion_certificacion_linea_certificacion', 'certificacion_linea', ['certificacion_id'], unique=False, schema='facturacion')
    op.create_index(op.f('ix_facturacion_certificacion_linea_organization_id'), 'certificacion_linea', ['organization_id'], unique=False, schema='facturacion')
    op.create_index('ix_facturacion_certificacion_linea_partida', 'certificacion_linea', ['partida_id'], unique=False, schema='facturacion')
    op.create_table('factura',
    sa.Column('codigo', sa.String(length=32), nullable=False),
    sa.Column('serie', sa.String(length=10), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=True),
    sa.Column('obra_id', sa.UUID(), nullable=False),
    sa.Column('certificacion_id', sa.UUID(), nullable=True),
    sa.Column('cliente_id', sa.UUID(), nullable=False),
    sa.Column('concepto', sa.String(length=250), nullable=False),
    sa.Column('fecha_emision', sa.Date(), nullable=True),
    sa.Column('fecha_vencimiento', sa.Date(), nullable=True),
    sa.Column('base_imponible', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('tipo_iva', sa.Enum('general', 'reducido', 'superreducido', 'exento', name='tipo_iva', native_enum=False, length=32), nullable=False),
    sa.Column('inversion_sujeto_pasivo', sa.Boolean(), nullable=False),
    sa.Column('cuota_iva', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('estado', sa.Enum('borrador', 'emitida', 'anulada', name='estado_factura', native_enum=False, length=32), nullable=False),
    sa.Column('motivo_anulacion', sa.Text(), nullable=True),
    sa.Column('notificado_n8n_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['certificacion_id'], ['facturacion.certificacion.id'], name=op.f('fk_factura_certificacion_id_certificacion'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['cliente_id'], ['terceros.tercero.id'], name=op.f('fk_factura_cliente_id_tercero'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['obra_id'], ['obras.obra.id'], name=op.f('fk_factura_obra_id_obra'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_factura_organization_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_factura')),
    sa.UniqueConstraint('organization_id', 'codigo', name='factura_codigo_unique'),
    sa.UniqueConstraint('organization_id', 'serie', 'numero', name='factura_serie_numero_unique'),
    schema='facturacion'
    )
    op.create_index('ix_facturacion_factura_certificacion', 'factura', ['certificacion_id'], unique=False, schema='facturacion')
    op.create_index('ix_facturacion_factura_cliente', 'factura', ['cliente_id'], unique=False, schema='facturacion')
    op.create_index('ix_facturacion_factura_obra', 'factura', ['obra_id'], unique=False, schema='facturacion')
    op.create_index(op.f('ix_facturacion_factura_organization_id'), 'factura', ['organization_id'], unique=False, schema='facturacion')
    op.create_table('cobro',
    sa.Column('factura_id', sa.UUID(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('importe', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('forma_pago', sa.Enum('transferencia', 'domiciliado', 'pagare', 'confirming', 'efectivo', 'tarjeta', name='forma_pago', native_enum=False, length=32), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['factura_id'], ['facturacion.factura.id'], name=op.f('fk_cobro_factura_id_factura'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_cobro_organization_id_organization'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cobro')),
    schema='facturacion'
    )
    op.create_index('ix_facturacion_cobro_factura', 'cobro', ['factura_id'], unique=False, schema='facturacion')
    op.create_index(op.f('ix_facturacion_cobro_organization_id'), 'cobro', ['organization_id'], unique=False, schema='facturacion')

    for tabla in ("certificacion", "certificacion_linea", "factura", "cobro"):
        activar_rls("facturacion", tabla)

    # Schema nuevo: sin esto el rol de mínimo privilegio no tiene ni USAGE
    # sobre él (lección de la Fase 7).
    conceder_privilegios_app("facturacion")


def downgrade() -> None:
    revocar_privilegios_app("facturacion")
    for tabla in ("cobro", "factura", "certificacion_linea", "certificacion"):
        desactivar_rls("facturacion", tabla)

    op.drop_index(op.f('ix_facturacion_cobro_organization_id'), table_name='cobro', schema='facturacion')
    op.drop_index('ix_facturacion_cobro_factura', table_name='cobro', schema='facturacion')
    op.drop_table('cobro', schema='facturacion')
    op.drop_index(op.f('ix_facturacion_factura_organization_id'), table_name='factura', schema='facturacion')
    op.drop_index('ix_facturacion_factura_obra', table_name='factura', schema='facturacion')
    op.drop_index('ix_facturacion_factura_cliente', table_name='factura', schema='facturacion')
    op.drop_index('ix_facturacion_factura_certificacion', table_name='factura', schema='facturacion')
    op.drop_table('factura', schema='facturacion')
    op.drop_index('ix_facturacion_certificacion_linea_partida', table_name='certificacion_linea', schema='facturacion')
    op.drop_index(op.f('ix_facturacion_certificacion_linea_organization_id'), table_name='certificacion_linea', schema='facturacion')
    op.drop_index('ix_facturacion_certificacion_linea_certificacion', table_name='certificacion_linea', schema='facturacion')
    op.drop_table('certificacion_linea', schema='facturacion')
    op.drop_index(op.f('ix_facturacion_certificacion_organization_id'), table_name='certificacion', schema='facturacion')
    op.drop_index('ix_facturacion_certificacion_obra', table_name='certificacion', schema='facturacion')
    op.drop_table('certificacion', schema='facturacion')
    op.execute("DROP SCHEMA IF EXISTS facturacion CASCADE")
