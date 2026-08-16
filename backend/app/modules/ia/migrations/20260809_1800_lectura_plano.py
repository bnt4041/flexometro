"""ia: lectura_plano

Segunda revisión de la rama `ia`: añade la lectura de planos vía Gemini
(Fase 10), encadenada tras `ia_0001`. `lectura_plano.partida_id` apunta a
presupuestos.partida.

Revision ID: ia_0002
Revises: ia_0001
Create Date: 2026-08-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ia_0002"
down_revision: str | None = "ia_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('lectura_plano',
    sa.Column('partida_id', sa.UUID(), nullable=True),
    sa.Column('fichero_nombre', sa.String(length=250), nullable=False),
    sa.Column('modelo', sa.String(length=60), nullable=False),
    sa.Column('observaciones', sa.Text(), nullable=True),
    sa.Column('respuesta_cruda', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('aplicada_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['core.organization.id'], name=op.f('fk_lectura_plano_organization_id_organization'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['partida_id'], ['presupuestos.partida.id'], name=op.f('fk_lectura_plano_partida_id_partida'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lectura_plano')),
    schema='ia'
    )
    op.create_index('ix_ia_lectura_plano_partida', 'lectura_plano', ['organization_id', 'partida_id'], unique=False, schema='ia')
    op.create_index(op.f('ix_ia_lectura_plano_organization_id'), 'lectura_plano', ['organization_id'], unique=False, schema='ia')

    from app.core.rls import activar_rls
    activar_rls("ia", "lectura_plano")
    # El schema "ia" ya recibió conceder_privilegios_app() en ia_0001; una
    # tabla nueva en un schema ya concedido no necesita repetirlo (ver
    # ALTER DEFAULT PRIVILEGES en esa migración).


def downgrade() -> None:
    from app.core.rls import desactivar_rls
    desactivar_rls("ia", "lectura_plano")

    op.drop_index(op.f('ix_ia_lectura_plano_organization_id'), table_name='lectura_plano', schema='ia')
    op.drop_index('ix_ia_lectura_plano_partida', table_name='lectura_plano', schema='ia')
    op.drop_table('lectura_plano', schema='ia')
