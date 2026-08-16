"""catalogo: familias, productos y precios de suministro

Rama propia, pero `depends_on` la encadena tras terceros: precio_suministro
tiene una clave ajena a terceros.tercero y sin esa dependencia el orden entre
ramas no estaría garantizado.

Revision ID: catalogo_0001
Revises:
Create Date: 2026-08-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "catalogo_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("catalogo",)
depends_on: str | Sequence[str] | None = ("terceros",)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS catalogo")

    op.create_table(
        "familia",
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_familia_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["catalogo.familia.id"],
            name=op.f("fk_familia_parent_id_familia"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_familia")),
        sa.UniqueConstraint("organization_id", "codigo", name="familia_codigo_unique"),
        schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_familia_organization_id"),
        "familia", ["organization_id"], unique=False, schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_familia_parent_id"),
        "familia", ["parent_id"], unique=False, schema="catalogo",
    )

    op.create_table(
        "producto",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "material", "mano_obra", "maquinaria", "servicio", "otro",
                name="tipo_producto", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("familia_id", sa.UUID(), nullable=True),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=False),
        sa.Column(
            "tipo_iva",
            sa.Enum(
                "general", "reducido", "superreducido", "exento",
                name="tipo_iva", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("precio_venta", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("ean", sa.String(length=14), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "origen_dato",
            sa.Enum(
                "manual", "fiebdc3", "ia", "importado",
                name="origen_dato", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("atributos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["familia_id"],
            ["catalogo.familia.id"],
            name=op.f("fk_producto_familia_id_familia"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_producto_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_producto")),
        sa.UniqueConstraint("organization_id", "codigo", name="producto_codigo_unique"),
        schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_producto_familia_id"),
        "producto", ["familia_id"], unique=False, schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_producto_organization_id"),
        "producto", ["organization_id"], unique=False, schema="catalogo",
    )
    op.create_index(
        "ix_catalogo_producto_resumen",
        "producto", ["organization_id", "resumen"], unique=False, schema="catalogo",
    )
    op.create_index(
        "ix_catalogo_producto_tipo",
        "producto", ["organization_id", "tipo"], unique=False, schema="catalogo",
    )

    op.create_table(
        "precio_suministro",
        sa.Column("producto_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("precio", sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column("moneda", sa.String(length=3), nullable=False),
        sa.Column("descuento", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("cantidad_minima", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("plazo_entrega_dias", sa.Integer(), nullable=True),
        sa.Column("referencia_proveedor", sa.String(length=60), nullable=True),
        sa.Column("vigente_desde", sa.Date(), nullable=False),
        sa.Column("vigente_hasta", sa.Date(), nullable=True),
        sa.Column("es_preferente", sa.Boolean(), nullable=False),
        sa.Column(
            "origen_dato",
            sa.Enum(
                "manual", "fiebdc3", "ia", "importado",
                name="origen_dato", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_precio_suministro_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["producto_id"],
            ["catalogo.producto.id"],
            name=op.f("fk_precio_suministro_producto_id_producto"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"],
            ["terceros.tercero.id"],
            name=op.f("fk_precio_suministro_proveedor_id_tercero"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_precio_suministro")),
        schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_precio_suministro_organization_id"),
        "precio_suministro", ["organization_id"], unique=False, schema="catalogo",
    )
    op.create_index(
        "ix_catalogo_precio_suministro_producto",
        "precio_suministro", ["organization_id", "producto_id"], unique=False, schema="catalogo",
    )
    op.create_index(
        "ix_catalogo_precio_suministro_proveedor",
        "precio_suministro", ["organization_id", "proveedor_id"], unique=False, schema="catalogo",
    )
    # Índice parcial: como mucho una tarifa preferente por producto.
    op.create_index(
        "uq_catalogo_precio_suministro_preferente",
        "precio_suministro", ["producto_id"], unique=True, schema="catalogo",
        postgresql_where=sa.text("es_preferente"),
    )


def downgrade() -> None:
    op.drop_table("precio_suministro", schema="catalogo")
    op.drop_table("producto", schema="catalogo")
    op.drop_table("familia", schema="catalogo")
    op.execute("DROP SCHEMA IF EXISTS catalogo CASCADE")
