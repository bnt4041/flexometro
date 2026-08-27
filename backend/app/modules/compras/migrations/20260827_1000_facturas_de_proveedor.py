"""compras: registro de facturas de proveedor

Lo que nos factura un proveedor, imputado a una obra, y qué albaranes cubre
cada factura — que es lo que permite cuadrar lo entregado con lo facturado.

No las emitimos nosotros: sin serie, sin numeración legal y sin nada del
circuito Veri*Factu. `codigo` es solo la referencia interna correlativa; lo que
identifica la factura frente al proveedor es SU número, y por eso hay un único
por (organización, proveedor, número): registrar dos veces la misma factura es
el camino corto a pagarla dos veces.

Revision ID: compras_0008
Revises: compras_0007
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "compras_0008"
down_revision: str | None = "compras_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factura_recibida",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("numero_proveedor", sa.String(length=60), nullable=False),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("base_imponible", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "tipo_iva",
            sa.Enum(
                "general", "reducido", "superreducido", "exento",
                name="tipo_iva", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="general",
        ),
        sa.Column(
            "inversion_sujeto_pasivo", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("cuota_iva", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "pagada",
                name="estado_factura_recibida", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("fecha_pago", sa.Date(), nullable=True),
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
            name=op.f("fk_factura_recibida_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_factura_recibida_obra_id_obra"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["terceros.tercero.id"],
            name=op.f("fk_factura_recibida_proveedor_id_tercero"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_recibida")),
        sa.UniqueConstraint(
            "organization_id", "codigo", name="factura_recibida_codigo_unique"
        ),
        sa.UniqueConstraint(
            "organization_id", "proveedor_id", "numero_proveedor",
            name="factura_recibida_numero_proveedor_unique",
        ),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_factura_recibida_organization_id"), "factura_recibida",
        ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_obra", "factura_recibida", ["obra_id"], schema="compras"
    )
    op.create_index(
        "ix_compras_factura_recibida_proveedor", "factura_recibida",
        ["proveedor_id"], schema="compras",
    )

    op.create_table(
        "factura_recibida_albaran",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("factura_id", sa.UUID(), nullable=False),
        sa.Column("albaran_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_factura_recibida_albaran_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["factura_id"], ["compras.factura_recibida.id"],
            name=op.f("fk_factura_recibida_albaran_factura_id_factura_recibida"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["albaran_id"], ["compras.albaran.id"],
            name=op.f("fk_factura_recibida_albaran_albaran_id_albaran"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_recibida_albaran")),
        sa.UniqueConstraint(
            "factura_id", "albaran_id", name="factura_recibida_albaran_unico"
        ),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_factura_recibida_albaran_organization_id"),
        "factura_recibida_albaran", ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_albaran_factura", "factura_recibida_albaran",
        ["factura_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_albaran_albaran", "factura_recibida_albaran",
        ["albaran_id"], schema="compras",
    )

    for tabla in ("factura_recibida", "factura_recibida_albaran"):
        activar_rls("compras", tabla)
    conceder_privilegios_app("compras")


def downgrade() -> None:
    for tabla in ("factura_recibida_albaran", "factura_recibida"):
        desactivar_rls("compras", tabla)
    op.drop_table("factura_recibida_albaran", schema="compras")
    op.drop_table("factura_recibida", schema="compras")
