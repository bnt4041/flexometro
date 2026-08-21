"""ia: sugerencia_patron

Rama propia encadenada tras presupuestos: `sugerencia_patron.plantilla_id`
apunta a presupuestos.presupuesto cuando la sugerencia se acepta.

Revision ID: ia_0001
Revises:
Create Date: 2026-08-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "ia_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("ia",)
depends_on: str | Sequence[str] | None = ("presupuestos", "core_0003")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ia")

    op.create_table('sugerencia_patron',
    sa.Column('tipo_obra', sa.String(length=120), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('modelo', sa.String(length=60), nullable=False),
    sa.Column('estadisticas_enviadas', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('sugerencia', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('plantilla_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_sugerencia_patron_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['plantilla_id'], ['presupuestos.presupuesto.id'], name=op.f('fk_sugerencia_patron_plantilla_id_presupuesto'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sugerencia_patron')),
    schema='ia'
    )
    op.create_index('ix_ia_sugerencia_patron_tipo_obra', 'sugerencia_patron', ['organization_id', 'tipo_obra'], unique=False, schema='ia')
    op.create_index(op.f('ix_ia_sugerencia_patron_organization_id'), 'sugerencia_patron', ['organization_id'], unique=False, schema='ia')

    activar_rls("ia", "sugerencia_patron")

    # Schema nuevo: sin esto el rol de mínimo privilegio no tiene ni USAGE
    # sobre él (lección de la Fase 7).
    conceder_privilegios_app("ia")


def downgrade() -> None:
    revocar_privilegios_app("ia")
    desactivar_rls("ia", "sugerencia_patron")

    op.drop_index(op.f('ix_ia_sugerencia_patron_organization_id'), table_name='sugerencia_patron', schema='ia')
    op.drop_index('ix_ia_sugerencia_patron_tipo_obra', table_name='sugerencia_patron', schema='ia')
    op.drop_table('sugerencia_patron', schema='ia')
    op.execute("DROP SCHEMA IF EXISTS ia CASCADE")
