"""web y redes sociales de empresa

Revision ID: e58b2d0f4a73
Revises: d47a1c9e2b60
Create Date: 2026-08-22 17:00:00

Fase 41: web, LinkedIn, Instagram, Facebook y X/Twitter por empresa — mismo
criterio que el resto de datos básicos, de referencia visual para cabeceras
de documentos y como claves de las plantillas Word.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e58b2d0f4a73'
down_revision: str | None = 'd47a1c9e2b60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('organization', sa.Column('web', sa.String(length=255), nullable=True), schema='core')
    op.add_column('organization', sa.Column('linkedin', sa.String(length=255), nullable=True), schema='core')
    op.add_column('organization', sa.Column('instagram', sa.String(length=255), nullable=True), schema='core')
    op.add_column('organization', sa.Column('facebook', sa.String(length=255), nullable=True), schema='core')
    op.add_column('organization', sa.Column('twitter', sa.String(length=255), nullable=True), schema='core')


def downgrade() -> None:
    op.drop_column('organization', 'twitter', schema='core')
    op.drop_column('organization', 'facebook', schema='core')
    op.drop_column('organization', 'instagram', schema='core')
    op.drop_column('organization', 'linkedin', schema='core')
    op.drop_column('organization', 'web', schema='core')
