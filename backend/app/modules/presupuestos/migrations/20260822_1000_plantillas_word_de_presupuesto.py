"""plantillas word de presupuesto

Revision ID: presupuestos_0010
Revises: presupuestos_0009
Create Date: 2026-08-22 10:00:00

Fase 39: plantillas Word con "llaves" ({{ presupuesto.codigo }}, etc.) que el
admin de cada cuenta puede subir para exportar el presupuesto con su propio
diseño, en PDF o Word. Escala de `cuenta_id`, no de `organization_id` —mismo
criterio que `core.patron_numeracion`—: es un recurso de ajustes compartido
por toda la cuenta, no un dato de negocio que deba aislarse por organización,
así que no lleva RLS. `cuenta_id` nulo marca las plantillas "de sistema" (una
por cada PDF fijo que este cambio retira), que se siembran solas al arrancar
la API (ver `plantilla_docx_service.asegurar_plantillas_sistema`).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'presupuestos_0010'
down_revision: str | None = 'presupuestos_0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'plantilla_docx',
        sa.Column('cuenta_id', sa.UUID(), nullable=True),
        sa.Column('es_sistema', sa.Boolean(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('archivo_docx_key', sa.String(length=500), nullable=False),
        sa.Column('claves_detectadas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('creado_por_subject', sa.String(length=120), nullable=True),
        sa.Column('creado_por_nombre', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ['cuenta_id'], ['core.cuenta.id'], name=op.f('fk_plantilla_docx_cuenta_id_cuenta'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_plantilla_docx')),
        sa.UniqueConstraint('archivo_docx_key', name=op.f('uq_plantilla_docx_archivo_docx_key')),
        schema='presupuestos',
    )


def downgrade() -> None:
    op.drop_table('plantilla_docx', schema='presupuestos')
