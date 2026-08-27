"""obras: el árbol propio de la obra

Capítulos, partidas y mediciones de la OBRA, separados de los del presupuesto.
El presupuesto es lo firmado con el cliente y no se vuelve a tocar; en obra la
medición cambia cada semana. Al vincular un presupuesto se copia su árbol aquí
y desde ese momento van por su cuenta, conservando el rastro de origen para
poder comparar ejecutado contra contratado.

Las tres tablas nacen vacías: el árbol de la obra que ya existe no se rellena
aquí. Se copia al vincular, y para la obra existente eso significa desvincular
y volver a vincular su presupuesto, o crear el árbol a mano. Rellenarlo en la
migración exigiría decidir por el usuario qué presupuesto manda, y esta obra ya
tiene mediciones propias en su presupuesto que no quiero duplicar a ciegas.

Revision ID: obras_0004
Revises: obras_0003
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "obras_0004"
down_revision: str | None = "obras_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "capitulo_obra",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("origen_presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("origen_capitulo_id", sa.UUID(), nullable=True),
        sa.Column(
            "es_anexo", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_capitulo_obra_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_capitulo_obra_obra_id_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["obras.capitulo_obra.id"],
            name=op.f("fk_capitulo_obra_parent_id_capitulo_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["origen_presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_capitulo_obra_origen_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["origen_capitulo_id"], ["presupuestos.capitulo.id"],
            name=op.f("fk_capitulo_obra_origen_capitulo_id_capitulo"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capitulo_obra")),
        schema="obras",
    )
    op.create_index(
        op.f("ix_obras_capitulo_obra_organization_id"), "capitulo_obra",
        ["organization_id"], schema="obras",
    )
    op.create_index(
        "ix_obras_capitulo_obra_obra", "capitulo_obra", ["obra_id"], schema="obras"
    )
    op.create_index(
        "ix_obras_capitulo_obra_parent", "capitulo_obra", ["parent_id"], schema="obras"
    )

    op.create_table(
        "partida_obra",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("capitulo_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=False, server_default="ud"),
        sa.Column("precio", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "precio_venta", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("medicion", sa.Numeric(14, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("importe", sa.Numeric(16, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "importe_venta", sa.Numeric(16, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("origen_presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("origen_partida_id", sa.UUID(), nullable=True),
        sa.Column(
            "es_anexo", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_partida_obra_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_partida_obra_obra_id_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["capitulo_id"], ["obras.capitulo_obra.id"],
            name=op.f("fk_partida_obra_capitulo_id_capitulo_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["origen_presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_partida_obra_origen_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["origen_partida_id"], ["presupuestos.partida.id"],
            name=op.f("fk_partida_obra_origen_partida_id_partida"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partida_obra")),
        schema="obras",
    )
    op.create_index(
        op.f("ix_obras_partida_obra_organization_id"), "partida_obra",
        ["organization_id"], schema="obras",
    )
    op.create_index(
        "ix_obras_partida_obra_obra", "partida_obra", ["obra_id"], schema="obras"
    )
    op.create_index(
        "ix_obras_partida_obra_capitulo", "partida_obra", ["capitulo_id"], schema="obras"
    )

    op.create_table(
        "medicion_obra",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("partida_id", sa.UUID(), nullable=False),
        sa.Column("comentario", sa.String(length=250), nullable=True),
        sa.Column("uds", sa.Numeric(14, 3), nullable=True),
        sa.Column("longitud", sa.Numeric(14, 3), nullable=True),
        sa.Column("anchura", sa.Numeric(14, 3), nullable=True),
        sa.Column("altura", sa.Numeric(14, 3), nullable=True),
        sa.Column("parcial", sa.Numeric(14, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_medicion_obra_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["obras.partida_obra.id"],
            name=op.f("fk_medicion_obra_partida_id_partida_obra"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medicion_obra")),
        schema="obras",
    )
    op.create_index(
        op.f("ix_obras_medicion_obra_organization_id"), "medicion_obra",
        ["organization_id"], schema="obras",
    )
    op.create_index(
        "ix_obras_medicion_obra_partida", "medicion_obra", ["partida_id"], schema="obras"
    )

    for tabla in ("capitulo_obra", "partida_obra", "medicion_obra"):
        activar_rls("obras", tabla)
    conceder_privilegios_app("obras")


def downgrade() -> None:
    for tabla in ("medicion_obra", "partida_obra", "capitulo_obra"):
        desactivar_rls("obras", tabla)
    op.drop_table("medicion_obra", schema="obras")
    op.drop_table("partida_obra", schema="obras")
    op.drop_table("capitulo_obra", schema="obras")
