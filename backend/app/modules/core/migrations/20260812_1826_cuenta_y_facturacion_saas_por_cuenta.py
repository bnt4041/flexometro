"""cuenta y facturacion saas por cuenta

Revision ID: 8fc5b0cfbcbf
Revises: b7561edc2c04
Create Date: 2026-08-12 18:26:59.347963

Fase 14: introduce `Cuenta` por encima de `Organization` y mueve la
facturación SaaS (tarifa asignada, cobros, descuentos aplicados) de
Organización a Cuenta. Backfill: una Cuenta nueva por cada Organización
existente, heredando su nombre y su tarifa asignada — ninguna organización
actual pierde su tarifa ni queda sin cuenta. `organizacion_descuento` se
renombra a `cuenta_descuento` conservando el histórico (no se recrea vacía).
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '8fc5b0cfbcbf'
down_revision: str | None = 'b7561edc2c04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. Tabla cuenta ---
    op.create_table('cuenta',
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('tarifa_id', sa.UUID(), nullable=True),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tarifa_id'], ['core.tarifa.id'], name=op.f('fk_cuenta_tarifa_id_tarifa'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cuenta')),
    schema='core'
    )

    # --- 2. Backfill: una cuenta por organización existente, heredando
    #     nombre y tarifa_id. Diccionario en memoria porque el volumen es
    #     "número de organizaciones", nunca masivo. ---
    organizaciones = conn.execute(
        sa.text('SELECT id, name, tarifa_id FROM core.organization')
    ).fetchall()
    cuenta_de_organizacion: dict[uuid.UUID, uuid.UUID] = {}
    for org_id, nombre, tarifa_id in organizaciones:
        cuenta_id = uuid.uuid4()
        conn.execute(
            sa.text(
                'INSERT INTO core.cuenta (id, nombre, is_active, tarifa_id, settings, created_at, updated_at) '
                "VALUES (:id, :nombre, true, :tarifa_id, '{}'::jsonb, now(), now())"
            ),
            {'id': cuenta_id, 'nombre': nombre, 'tarifa_id': tarifa_id},
        )
        cuenta_de_organizacion[org_id] = cuenta_id

    # --- 3. organization.cuenta_id (nullable primero para poder rellenar) ---
    op.add_column('organization', sa.Column('cuenta_id', sa.UUID(), nullable=True), schema='core')
    for org_id, cuenta_id in cuenta_de_organizacion.items():
        conn.execute(
            sa.text('UPDATE core.organization SET cuenta_id = :cuenta_id WHERE id = :org_id'),
            {'cuenta_id': cuenta_id, 'org_id': org_id},
        )
    op.alter_column('organization', 'cuenta_id', nullable=False, schema='core')
    op.create_index(op.f('ix_core_organization_cuenta_id'), 'organization', ['cuenta_id'], unique=False, schema='core')
    op.drop_constraint(op.f('fk_organization_tarifa_id_tarifa'), 'organization', schema='core', type_='foreignkey')
    op.create_foreign_key(op.f('fk_organization_cuenta_id_cuenta'), 'organization', 'cuenta', ['cuenta_id'], ['id'], source_schema='core', referent_schema='core', ondelete='RESTRICT')
    op.drop_column('organization', 'tarifa_id', schema='core')

    # --- 4. cobro_saas: organization_id -> cuenta_id (backfill vía join) ---
    op.add_column('cobro_saas', sa.Column('cuenta_id', sa.UUID(), nullable=True), schema='core')
    conn.execute(sa.text(
        'UPDATE core.cobro_saas cs SET cuenta_id = o.cuenta_id '
        'FROM core.organization o WHERE cs.organization_id = o.id'
    ))
    op.alter_column('cobro_saas', 'cuenta_id', nullable=False, schema='core')
    op.drop_index(op.f('ix_core_cobro_saas_organization'), table_name='cobro_saas', schema='core')
    op.create_index('ix_core_cobro_saas_cuenta', 'cobro_saas', ['cuenta_id'], unique=False, schema='core')
    op.drop_constraint(op.f('fk_cobro_saas_organization_id_organization'), 'cobro_saas', schema='core', type_='foreignkey')
    op.create_foreign_key(op.f('fk_cobro_saas_cuenta_id_cuenta'), 'cobro_saas', 'cuenta', ['cuenta_id'], ['id'], source_schema='core', referent_schema='core', ondelete='CASCADE')
    op.drop_column('cobro_saas', 'organization_id', schema='core')

    # --- 5. organizacion_descuento -> cuenta_descuento: RENOMBRAR, no
    #     recrear — conserva el histórico de aplicaciones/anulaciones. La FK
    #     antigua apunta a organization y hay que quitarla ANTES de escribir
    #     valores de cuenta en la columna (violarían esa FK). ---
    op.drop_constraint('fk_organizacion_descuento_organization_id_organization', 'organizacion_descuento', schema='core', type_='foreignkey')
    op.drop_index('ix_core_organizacion_descuento_organization', table_name='organizacion_descuento', schema='core')
    op.rename_table('organizacion_descuento', 'cuenta_descuento', schema='core')
    op.alter_column('cuenta_descuento', 'organization_id', new_column_name='cuenta_id', schema='core')
    conn.execute(sa.text(
        'UPDATE core.cuenta_descuento cd SET cuenta_id = o.cuenta_id '
        'FROM core.organization o WHERE cd.cuenta_id = o.id'
    ))
    op.create_index('ix_core_cuenta_descuento_cuenta', 'cuenta_descuento', ['cuenta_id'], unique=False, schema='core')
    op.create_foreign_key(op.f('fk_cuenta_descuento_cuenta_id_cuenta'), 'cuenta_descuento', 'cuenta', ['cuenta_id'], ['id'], source_schema='core', referent_schema='core', ondelete='CASCADE')
    # El nombre del constraint de PK sigue siendo el antiguo tras el rename
    # (Postgres no lo renombra solo); se deja tal cual, es puramente
    # cosmético y no afecta a nada funcional.


def downgrade() -> None:
    """Reversión best-effort: asume que sigue habiendo como mucho UNA
    organización por cuenta (cierto justo tras el upgrade). Si la Fase 15+
    ya ha añadido una segunda organización a alguna cuenta, esta reversión
    pierde esa asociación adicional — no hay forma no ambigua de decidir a
    cuál de varias organizaciones de una cuenta le "toca" volver a llevar la
    tarifa/cobros/descuentos de esa cuenta."""
    conn = op.get_bind()

    op.drop_constraint(op.f('fk_cuenta_descuento_cuenta_id_cuenta'), 'cuenta_descuento', schema='core', type_='foreignkey')
    op.drop_index('ix_core_cuenta_descuento_cuenta', table_name='cuenta_descuento', schema='core')
    conn.execute(sa.text(
        'UPDATE core.cuenta_descuento cd SET cuenta_id = o.id '
        'FROM core.organization o WHERE cd.cuenta_id = o.cuenta_id'
    ))
    op.alter_column('cuenta_descuento', 'cuenta_id', new_column_name='organization_id', schema='core')
    op.rename_table('cuenta_descuento', 'organizacion_descuento', schema='core')
    op.create_index('ix_core_organizacion_descuento_organization', 'organizacion_descuento', ['organization_id'], unique=False, schema='core')
    op.create_foreign_key('fk_organizacion_descuento_organization_id_organization', 'organizacion_descuento', 'organization', ['organization_id'], ['id'], source_schema='core', referent_schema='core', ondelete='CASCADE')

    op.add_column('cobro_saas', sa.Column('organization_id', sa.UUID(), nullable=True), schema='core')
    conn.execute(sa.text(
        'UPDATE core.cobro_saas cs SET organization_id = o.id '
        'FROM core.organization o WHERE cs.cuenta_id = o.cuenta_id'
    ))
    op.alter_column('cobro_saas', 'organization_id', nullable=False, schema='core')
    op.drop_constraint(op.f('fk_cobro_saas_cuenta_id_cuenta'), 'cobro_saas', schema='core', type_='foreignkey')
    op.create_foreign_key(op.f('fk_cobro_saas_organization_id_organization'), 'cobro_saas', 'organization', ['organization_id'], ['id'], source_schema='core', referent_schema='core', ondelete='CASCADE')
    op.drop_index('ix_core_cobro_saas_cuenta', table_name='cobro_saas', schema='core')
    op.create_index(op.f('ix_core_cobro_saas_organization'), 'cobro_saas', ['organization_id'], unique=False, schema='core')
    op.drop_column('cobro_saas', 'cuenta_id', schema='core')

    op.add_column('organization', sa.Column('tarifa_id', sa.UUID(), nullable=True), schema='core')
    conn.execute(sa.text(
        'UPDATE core.organization o SET tarifa_id = c.tarifa_id '
        'FROM core.cuenta c WHERE o.cuenta_id = c.id'
    ))
    op.drop_constraint(op.f('fk_organization_cuenta_id_cuenta'), 'organization', schema='core', type_='foreignkey')
    op.create_foreign_key(op.f('fk_organization_tarifa_id_tarifa'), 'organization', 'tarifa', ['tarifa_id'], ['id'], source_schema='core', referent_schema='core', ondelete='SET NULL')
    op.drop_index(op.f('ix_core_organization_cuenta_id'), table_name='organization', schema='core')
    op.drop_column('organization', 'cuenta_id', schema='core')

    op.drop_table('cuenta', schema='core')
