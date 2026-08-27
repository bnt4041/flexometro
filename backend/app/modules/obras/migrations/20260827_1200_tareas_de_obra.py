"""obras: gestor de tareas

Lo que hay que hacer en una obra, con estados para el tablero kanban.

El responsable es `Personal`, no un usuario de Keycloak: en obra se asigna al
encargado o al oficial que está allí, y ese es alguien de la plantilla aunque no
tenga cuenta en la aplicación. SET NULL para que dar de baja a un trabajador no
borre la tarea.

Revision ID: obras_0006
Revises: obras_0005
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "obras_0006"
down_revision: str | None = "obras_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tarea",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("titulo", sa.String(length=250), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("responsable_id", sa.UUID(), nullable=True),
        sa.Column("fecha_limite", sa.Date(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "en_curso", "hecha",
                name="estado_tarea", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column(
            "prioridad",
            sa.Enum(
                "baja", "normal", "alta",
                name="prioridad_tarea", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completada_en", sa.Date(), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_tarea_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_tarea_obra_id_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["responsable_id"], ["obras.personal.id"],
            name=op.f("fk_tarea_responsable_id_personal"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tarea")),
        schema="obras",
    )
    op.create_index(
        op.f("ix_obras_tarea_organization_id"), "tarea",
        ["organization_id"], schema="obras",
    )
    op.create_index("ix_obras_tarea_obra", "tarea", ["obra_id"], schema="obras")
    op.create_index(
        "ix_obras_tarea_estado", "tarea", ["obra_id", "estado"], schema="obras"
    )

    activar_rls("obras", "tarea")
    conceder_privilegios_app("obras")


def downgrade() -> None:
    desactivar_rls("obras", "tarea")
    op.drop_table("tarea", schema="obras")
