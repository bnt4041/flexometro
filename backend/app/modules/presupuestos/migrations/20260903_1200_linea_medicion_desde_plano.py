"""presupuestos: de qué elemento de un plano sale una línea de medición

Espejo de `planos.elemento_plano.linea_medicion_id` (que apunta hacia aquí)
pero en el otro sentido, para poder preguntar «¿esta línea viene de un
plano?» sin tener que consultar el módulo de planos. Sin FK a propósito,
igual que la columna que refleja: los dos módulos son de esquemas
independientes y `planos` puede no estar activado en esta organización — una
FK entre ellos ataría el ciclo de vida de una a la otra sin necesidad.

Revision ID: presupuestos_0013
Revises: presupuestos_0012
Create Date: 2026-09-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'presupuestos_0013'
down_revision: str | None = 'presupuestos_0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'presupuestos'


def upgrade() -> None:
    op.add_column(
        'linea_medicion',
        sa.Column('desde_plano_elemento_id', postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column('linea_medicion', 'desde_plano_elemento_id', schema=SCHEMA)
