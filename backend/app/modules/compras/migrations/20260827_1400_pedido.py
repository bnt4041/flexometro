"""compras: pedidos a proveedor

La orden de compra en firme — el paso intermedio entre pedir precio
(`solicitud_precios`) y lo que entra físicamente en obra (`albaran`). Puede
venir de confirmar la oferta ganadora de una solicitud ya resuelta
(`origen_solicitud_id`/`origen_oferta_presupuesto_id`, ambos NULL si no) o
crearse directo a un proveedor conocido.

`albaran` gana `pedido_id` opcional: de qué pedido viene esa entrega. SET
NULL en los dos sentidos: borrar el pedido no borra la entrega ya recibida,
y un albarán se puede seguir dando de alta sin pedido de por medio.

Revision ID: compras_0009
Revises: compras_0008
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, desactivar_rls

revision: str = "compras_0009"
down_revision: str | None = "compras_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pedido",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("origen_solicitud_id", sa.UUID(), nullable=True),
        sa.Column("origen_oferta_presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("fecha_entrega_prevista", sa.Date(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "confirmado", "servido_parcial", "servido", "cancelado",
                name="estado_pedido", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("notas", sa.Text(), nullable=True),
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
            name=op.f("fk_pedido_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_pedido_obra_id_obra"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["terceros.tercero.id"],
            name=op.f("fk_pedido_proveedor_id_tercero"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origen_solicitud_id"], ["compras.solicitud_precios.id"],
            name=op.f("fk_pedido_origen_solicitud_id_solicitud_precios"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["origen_oferta_presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_pedido_origen_oferta_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido")),
        sa.UniqueConstraint("organization_id", "codigo", name="pedido_codigo_unique"),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_pedido_organization_id"), "pedido", ["organization_id"], schema="compras",
    )
    op.create_index("ix_compras_pedido_obra", "pedido", ["obra_id"], schema="compras")
    op.create_index("ix_compras_pedido_proveedor", "pedido", ["proveedor_id"], schema="compras")

    op.create_table(
        "pedido_linea",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("pedido_id", sa.UUID(), nullable=False),
        sa.Column("concepto_id", sa.UUID(), nullable=True),
        sa.Column("descripcion", sa.String(length=250), nullable=False),
        sa.Column("unidad", sa.String(length=10), nullable=False, server_default="ud"),
        sa.Column("cantidad", sa.Numeric(14, 3), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(14, 4), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_pedido_linea_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"], ["compras.pedido.id"],
            name=op.f("fk_pedido_linea_pedido_id_pedido"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concepto_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_pedido_linea_concepto_id_concepto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_linea")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_pedido_linea_organization_id"), "pedido_linea",
        ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_pedido_linea_pedido", "pedido_linea", ["pedido_id"], schema="compras"
    )

    op.add_column(
        "albaran", sa.Column("pedido_id", sa.UUID(), nullable=True), schema="compras"
    )
    op.create_foreign_key(
        op.f("fk_albaran_pedido_id_pedido"), "albaran", "pedido",
        ["pedido_id"], ["id"], source_schema="compras", referent_schema="compras",
        ondelete="SET NULL",
    )
    op.create_index("ix_compras_albaran_pedido", "albaran", ["pedido_id"], schema="compras")

    for tabla in ("pedido", "pedido_linea"):
        activar_rls("compras", tabla)


def downgrade() -> None:
    op.drop_index("ix_compras_albaran_pedido", table_name="albaran", schema="compras")
    op.drop_constraint(
        op.f("fk_albaran_pedido_id_pedido"), "albaran", schema="compras", type_="foreignkey"
    )
    op.drop_column("albaran", "pedido_id", schema="compras")

    for tabla in ("pedido_linea", "pedido"):
        desactivar_rls("compras", tabla)
    op.drop_table("pedido_linea", schema="compras")
    op.drop_table("pedido", schema="compras")
