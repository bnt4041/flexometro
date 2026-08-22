"""politica de privacidad por empresa

Revision ID: d47a1c9e2b60
Revises: c2f5e8d03b12
Create Date: 2026-08-22 16:00:00

Fase 41: texto enriquecido (HTML) propio de cada organización/empresa, no
de la cuenta — cada CIF puede tener su propia política de privacidad.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd47a1c9e2b60'
down_revision: str | None = 'c2f5e8d03b12'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('organization', sa.Column('politica_privacidad', sa.Text(), nullable=True), schema='core')


def downgrade() -> None:
    op.drop_column('organization', 'politica_privacidad', schema='core')
