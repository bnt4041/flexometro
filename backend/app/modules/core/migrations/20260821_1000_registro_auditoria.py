"""registro de auditoria (historial de cambios)

Revision ID: 260c71294d89
Revises: db433ad465d8
Create Date: 2026-08-21 10:00:00

Fase 38: tabla genérica de historial de cambios, rellenada por el listener
de sesión de `app.core.auditoria` (antes/después por campo, quién y cuándo)
para cualquier modelo con `AutoriaMixin` — ver el docstring de
`app/modules/core/auditoria_models.py`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import activar_rls, desactivar_rls

revision: str = '260c71294d89'
down_revision: str | None = 'db433ad465d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'registro_auditoria',
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tabla', sa.String(length=80), nullable=False),
        sa.Column('registro_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'accion',
            sa.Enum('creado', 'modificado', 'eliminado', name='accion_auditoria', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column('cambios', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('usuario_subject', sa.String(length=120), nullable=True),
        sa.Column('usuario_nombre', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['core.organization.id'],
            name=op.f('fk_registro_auditoria_organization_id_organization'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_registro_auditoria')),
        schema='core',
    )
    op.create_index(
        op.f('ix_core_registro_auditoria_organization_id'), 'registro_auditoria',
        ['organization_id'], unique=False, schema='core',
    )
    op.create_index(
        'ix_core_registro_auditoria_registro', 'registro_auditoria',
        ['tabla', 'registro_id'], unique=False, schema='core',
    )

    # El schema `core` ya tiene los privilegios del rol de mínimo privilegio
    # concedidos desde `core_0003` (ALTER DEFAULT PRIVILEGES) — no hace falta
    # GRANT aquí. Sí lleva RLS: cualquier usuario de la organización puede
    # leer su propio historial, no solo superadmin.
    activar_rls('core', 'registro_auditoria')


def downgrade() -> None:
    desactivar_rls('core', 'registro_auditoria')

    op.drop_index('ix_core_registro_auditoria_registro', table_name='registro_auditoria', schema='core')
    op.drop_index(op.f('ix_core_registro_auditoria_organization_id'), table_name='registro_auditoria', schema='core')
    op.drop_table('registro_auditoria', schema='core')
