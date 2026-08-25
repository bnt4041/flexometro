"""presupuestos: distinguir presupuesto de cliente de oferta de proveedor

La oferta que devuelve un proveedor a una solicitud de precios comparte tabla
con el presupuesto de cliente en vez de un árbol paralelo — capítulos,
partidas, mediciones y descompuestos son la misma estructura, solo cambia qué
lado del negocio la generó. `tipo` distingue las dos vistas; `proveedor_id`
es el equivalente de `cliente_id` para las de tipo proveedor.

Revision ID: presupuestos_0012
Revises: presupuestos_0011
Create Date: 2026-08-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'presupuestos_0012'
down_revision: str | None = 'presupuestos_0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'presupuesto',
        sa.Column(
            'tipo',
            sa.Enum('cliente', 'proveedor', name='tipo_presupuesto', native_enum=False, length=32),
            nullable=False,
            server_default='cliente',
        ),
        schema='presupuestos',
    )
    # server_default solo para rellenar lo ya existente; las altas nuevas lo
    # ponen el ORM.
    op.alter_column('presupuesto', 'tipo', server_default=None, schema='presupuestos')

    op.add_column(
        'presupuesto',
        sa.Column('proveedor_id', sa.UUID(), nullable=True),
        schema='presupuestos',
    )
    op.create_foreign_key(
        op.f('fk_presupuesto_proveedor_id_tercero'),
        'presupuesto', 'tercero',
        ['proveedor_id'], ['id'],
        source_schema='presupuestos', referent_schema='terceros',
        ondelete='RESTRICT',
    )
    op.create_index(
        op.f('ix_presupuestos_presupuesto_proveedor_id'), 'presupuesto', ['proveedor_id'],
        schema='presupuestos',
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_presupuestos_presupuesto_proveedor_id'), table_name='presupuesto',
        schema='presupuestos',
    )
    op.drop_constraint(
        op.f('fk_presupuesto_proveedor_id_tercero'), 'presupuesto',
        schema='presupuestos', type_='foreignkey',
    )
    op.drop_column('presupuesto', 'proveedor_id', schema='presupuestos')
    op.drop_column('presupuesto', 'tipo', schema='presupuestos')
