"""compras: albarán y línea de albarán

Rama propia encadenada tras obras y catalogo: `albaran.obra_id` apunta a
obras.obra, `albaran_linea.producto_id` a catalogo.producto y
`albaran_linea.capitulo_id` a presupuestos.capitulo (ya garantizado por la
cadena de dependencias de la rama `obras`).

Revision ID: compras_0001
Revises:
Create Date: 2026-08-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "compras_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("compras",)
depends_on: str | Sequence[str] | None = ("obras", "catalogo", "core_0003")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS compras")

    op.create_table(
        "albaran",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("numero_proveedor", sa.String(length=60), nullable=True),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "borrador", "conformado", "facturado",
                name="estado_albaran", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_albaran_obra_id_obra"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_albaran_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["terceros.tercero.id"],
            name=op.f("fk_albaran_proveedor_id_tercero"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_albaran")),
        sa.UniqueConstraint("organization_id", "codigo", name="albaran_codigo_unique"),
        schema="compras",
    )
    op.create_index("ix_compras_albaran_obra", "albaran", ["obra_id"], schema="compras")
    op.create_index(
        op.f("ix_compras_albaran_organization_id"), "albaran", ["organization_id"], schema="compras"
    )
    op.create_index("ix_compras_albaran_proveedor", "albaran", ["proveedor_id"], schema="compras")

    op.create_table(
        "albaran_linea",
        sa.Column("albaran_id", sa.UUID(), nullable=False),
        sa.Column("producto_id", sa.UUID(), nullable=True),
        sa.Column("capitulo_id", sa.UUID(), nullable=True),
        sa.Column("descripcion", sa.String(length=250), nullable=False),
        sa.Column("unidad", sa.String(length=10), nullable=False),
        sa.Column("cantidad", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("importe", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["albaran_id"], ["compras.albaran.id"],
            name=op.f("fk_albaran_linea_albaran_id_albaran"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["capitulo_id"], ["presupuestos.capitulo.id"],
            name=op.f("fk_albaran_linea_capitulo_id_capitulo"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_albaran_linea_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["producto_id"], ["catalogo.producto.id"],
            name=op.f("fk_albaran_linea_producto_id_producto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_albaran_linea")),
        schema="compras",
    )
    op.create_index(
        "ix_compras_albaran_linea_albaran", "albaran_linea", ["albaran_id"], schema="compras"
    )
    op.create_index(
        "ix_compras_albaran_linea_capitulo", "albaran_linea", ["capitulo_id"], schema="compras"
    )
    op.create_index(
        op.f("ix_compras_albaran_linea_organization_id"), "albaran_linea", ["organization_id"],
        schema="compras",
    )

    for tabla in ("albaran", "albaran_linea"):
        activar_rls("compras", tabla)

    conceder_privilegios_app("compras")


def downgrade() -> None:
    revocar_privilegios_app("compras")

    for tabla in ("albaran_linea", "albaran"):
        desactivar_rls("compras", tabla)

    op.drop_table("albaran_linea", schema="compras")
    op.drop_table("albaran", schema="compras")
    op.execute("DROP SCHEMA IF EXISTS compras CASCADE")
