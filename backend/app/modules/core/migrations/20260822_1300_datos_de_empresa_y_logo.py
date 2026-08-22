"""datos de empresa y logo en organization

Revision ID: b1e4d7c92a01
Revises: a3e7f0c8d1b4
Create Date: 2026-08-22 13:00:00

Fase 40: datos básicos de la organización (dirección, contacto) y logo, para
que sirvan de referencia en cabeceras de documentos y como claves de las
plantillas Word de presupuesto (`organizacion.*`, ver
`plantilla_docx_service.contexto_plantilla`). El logo se guarda como objeto
en MinIO (`app/core/storage.py`), aquí solo su `object_key` y `content_type`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b1e4d7c92a01'
down_revision: str | None = 'a3e7f0c8d1b4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('organization', sa.Column('direccion', sa.String(length=255), nullable=True), schema='core')
    op.add_column('organization', sa.Column('codigo_postal', sa.String(length=12), nullable=True), schema='core')
    op.add_column('organization', sa.Column('ciudad', sa.String(length=120), nullable=True), schema='core')
    op.add_column('organization', sa.Column('provincia', sa.String(length=120), nullable=True), schema='core')
    op.add_column('organization', sa.Column('telefono', sa.String(length=30), nullable=True), schema='core')
    op.add_column('organization', sa.Column('email', sa.String(length=255), nullable=True), schema='core')
    op.add_column('organization', sa.Column('logo_object_key', sa.String(length=500), nullable=True), schema='core')
    op.add_column('organization', sa.Column('logo_content_type', sa.String(length=100), nullable=True), schema='core')


def downgrade() -> None:
    op.drop_column('organization', 'logo_content_type', schema='core')
    op.drop_column('organization', 'logo_object_key', schema='core')
    op.drop_column('organization', 'email', schema='core')
    op.drop_column('organization', 'telefono', schema='core')
    op.drop_column('organization', 'provincia', schema='core')
    op.drop_column('organization', 'ciudad', schema='core')
    op.drop_column('organization', 'codigo_postal', schema='core')
    op.drop_column('organization', 'direccion', schema='core')
