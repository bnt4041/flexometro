"""core: bandeja de notificaciones

Hasta ahora la aplicación solo sabía avisar por correo o con un aviso efímero
de cuatro segundos en pantalla. Esto añade avisos persistentes por
organización (o por usuario), que es lo que hace falta para que a un proveedor
que YA tiene Flexómetro le llegue una solicitud de precios dentro de su propia
aplicación en vez de por un enlace externo.

Revision ID: core_notif_0001
Revises: a71d4b6e5c90
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "core_notif_0001"
down_revision: str | None = "a71d4b6e5c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notificacion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("tipo", sa.String(length=48), nullable=False),
        sa.Column("destinatario_subject", sa.String(length=120), nullable=True),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=True),
        sa.Column("enlace", sa.String(length=500), nullable=True),
        sa.Column("importante", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("leida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resuelta_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_acceso", sa.String(length=200), nullable=True),
        sa.Column("presupuesto_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_notificacion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_notificacion_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notificacion")),
        schema="core",
    )
    op.create_index(
        op.f("ix_core_notificacion_organization_id"), "notificacion",
        ["organization_id"], schema="core",
    )
    op.create_index(
        "ix_core_notificacion_bandeja", "notificacion",
        ["organization_id", "leida_en"], schema="core",
    )

    activar_rls("core", "notificacion")
    conceder_privilegios_app("core")


def downgrade() -> None:
    desactivar_rls("core", "notificacion")
    op.drop_table("notificacion", schema="core")
