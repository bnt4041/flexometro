"""descripcion en registro_auditoria

Revision ID: a3e7f0c8d1b4
Revises: f4a1c9e2b3d7
Create Date: 2026-08-21 12:00:00

Fase 38b: además de creado/modificado/eliminado (diffs de columnas), hace
falta un cuarto tipo de entrada — "evento": una acción del servidor que no
es un cambio de columna en la propia entidad (la IA añade un capítulo con
varias partidas, por ejemplo, y ninguna de las dos lleva `AutoriaMixin` —
ver `app/modules/core/auditoria_models.py`). `descripcion` es el texto libre
de esas entradas; `cambios` sigue siendo solo para los diffs estructurados.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3e7f0c8d1b4'
down_revision: str | None = 'f4a1c9e2b3d7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'registro_auditoria',
        sa.Column('descripcion', sa.Text(), nullable=True),
        schema='core',
    )


def downgrade() -> None:
    op.drop_column('registro_auditoria', 'descripcion', schema='core')
