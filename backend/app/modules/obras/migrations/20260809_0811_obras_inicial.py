"""obras: obra, personal, asignación y parte de trabajo

Rama propia encadenada tras presupuestos: `obra.presupuesto_id` apunta a
presupuestos.presupuesto, y `asignacion`/`parte_trabajo` referencian
presupuestos.capitulo. Sin `depends_on` el orden entre ramas no está
garantizado.

Revision ID: obras_0001
Revises:
Create Date: 2026-08-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "obras_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("obras",)
depends_on: str | Sequence[str] | None = ("presupuestos",)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS obras")

    op.create_table(
        "personal",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("apellidos", sa.String(length=160), nullable=True),
        sa.Column("categoria", sa.String(length=60), nullable=True),
        sa.Column("coste_hora", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_personal_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personal")),
        sa.UniqueConstraint("organization_id", "codigo", name="personal_codigo_unique"),
        schema="obras",
    )
    op.create_index(
        op.f("ix_obras_personal_organization_id"), "personal", ["organization_id"], schema="obras"
    )

    op.create_table(
        "obra",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=250), nullable=False),
        sa.Column("presupuesto_id", sa.UUID(), nullable=False),
        sa.Column("jefe_obra_id", sa.UUID(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "planificada", "en_ejecucion", "paralizada", "finalizada", "cerrada",
                name="estado_obra", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_fin_prevista", sa.Date(), nullable=True),
        sa.Column("fecha_fin_real", sa.Date(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["jefe_obra_id"], ["obras.personal.id"],
            name=op.f("fk_obra_jefe_obra_id_personal"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_obra_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_obra_presupuesto_id_presupuesto"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_obra")),
        sa.UniqueConstraint("organization_id", "codigo", name="obra_codigo_unique"),
        sa.UniqueConstraint("presupuesto_id", name="obra_presupuesto_unique"),
        schema="obras",
    )
    op.create_index("ix_obras_obra_estado", "obra", ["organization_id", "estado"], schema="obras")
    op.create_index(
        op.f("ix_obras_obra_organization_id"), "obra", ["organization_id"], schema="obras"
    )

    op.create_table(
        "asignacion",
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("personal_id", sa.UUID(), nullable=False),
        sa.Column("coste_hora", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("fecha_desde", sa.Date(), nullable=False),
        sa.Column("fecha_hasta", sa.Date(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_asignacion_obra_id_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_asignacion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["personal_id"], ["obras.personal.id"],
            name=op.f("fk_asignacion_personal_id_personal"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asignacion")),
        schema="obras",
    )
    op.create_index("ix_obras_asignacion_obra", "asignacion", ["obra_id"], schema="obras")
    op.create_index(
        op.f("ix_obras_asignacion_organization_id"), "asignacion", ["organization_id"], schema="obras"
    )
    op.create_index("ix_obras_asignacion_personal", "asignacion", ["personal_id"], schema="obras")

    op.create_table(
        "parte_trabajo",
        sa.Column("asignacion_id", sa.UUID(), nullable=False),
        sa.Column("capitulo_id", sa.UUID(), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("horas", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("coste", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["asignacion_id"], ["obras.asignacion.id"],
            name=op.f("fk_parte_trabajo_asignacion_id_asignacion"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["capitulo_id"], ["presupuestos.capitulo.id"],
            name=op.f("fk_parte_trabajo_capitulo_id_capitulo"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_parte_trabajo_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parte_trabajo")),
        sa.UniqueConstraint(
            "asignacion_id", "fecha", name="parte_trabajo_asignacion_fecha_unique"
        ),
        schema="obras",
    )
    op.create_index(
        "ix_obras_parte_trabajo_asignacion", "parte_trabajo", ["asignacion_id"], schema="obras"
    )
    op.create_index(
        "ix_obras_parte_trabajo_capitulo", "parte_trabajo", ["capitulo_id"], schema="obras"
    )
    op.create_index(
        op.f("ix_obras_parte_trabajo_organization_id"), "parte_trabajo", ["organization_id"],
        schema="obras",
    )

    for tabla in ("personal", "obra", "asignacion", "parte_trabajo"):
        activar_rls("obras", tabla)

    # El schema es nuevo: sin esto, el rol de mínimo privilegio de la API no
    # tiene ni USAGE sobre él y la primera consulta falla con "permission
    # denied for schema obras".
    conceder_privilegios_app("obras")


def downgrade() -> None:
    revocar_privilegios_app("obras")

    for tabla in ("parte_trabajo", "asignacion", "obra", "personal"):
        desactivar_rls("obras", tabla)

    op.drop_table("parte_trabajo", schema="obras")
    op.drop_table("asignacion", schema="obras")
    op.drop_table("obra", schema="obras")
    op.drop_table("personal", schema="obras")
    op.execute("DROP SCHEMA IF EXISTS obras CASCADE")
