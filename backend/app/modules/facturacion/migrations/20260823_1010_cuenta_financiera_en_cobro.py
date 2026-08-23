"""cuenta financiera en cobro

Revision ID: facturacion_0003
Revises: facturacion_0002
Create Date: 2026-08-23 10:10:00

Fase 44: en qué banco o caja entró cada cobro. Nullable — los cobros
anteriores a esta fase no lo saben, y forzar un valor inventado sería peor
que dejarlo en blanco.

`depends_on` apunta a la revisión CONCRETA que crea `core.cuenta_financiera`,
no a la etiqueta de rama `core`: una etiqueta de rama resuelve a la revisión
que la lleva (la raíz de la rama), no a su cabeza, así que con `("core",)`
esta migración podría correr antes de que la tabla exista al levantar una
base vacía de una sola pasada.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'facturacion_0003'
down_revision: str | None = 'facturacion_0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = ('a71d4b6e5c90',)


def upgrade() -> None:
    op.add_column('cobro', sa.Column('cuenta_financiera_id', sa.UUID(), nullable=True), schema='facturacion')
    op.create_foreign_key(
        op.f('fk_cobro_cuenta_financiera_id_cuenta_financiera'),
        'cobro',
        'cuenta_financiera',
        ['cuenta_financiera_id'],
        ['id'],
        source_schema='facturacion',
        referent_schema='core',
        ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_cobro_cuenta_financiera_id_cuenta_financiera'),
        'cobro',
        schema='facturacion',
        type_='foreignkey',
    )
    op.drop_column('cobro', 'cuenta_financiera_id', schema='facturacion')
