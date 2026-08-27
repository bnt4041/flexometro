"""contratos: alta del módulo

Formaliza el acuerdo de una obra, con el cliente (sobre el presupuesto
aprobado) o con un proveedor (marco/subcontrata), según `tipo`. Sin líneas:
el desglose de precio vive en el `Presupuesto` que enlaza, si lo hay.

Revision ID: contratos_0001
Revises:
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "contratos_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("contratos",)
depends_on: str | Sequence[str] | None = ("obras", "terceros", "core_0003")


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS contratos")

    op.create_table(
        "contrato",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum("cliente", "proveedor", name="tipo_contrato", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("cliente_id", sa.UUID(), nullable=True),
        sa.Column("proveedor_id", sa.UUID(), nullable=True),
        sa.Column("presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("fecha_firma", sa.Date(), nullable=True),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_fin_prevista", sa.Date(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "borrador", "firmado", "rescindido", "finalizado",
                name="estado_contrato", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="borrador",
        ),
        sa.Column("importe", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "retencion_garantia_pct", sa.Numeric(5, 2), nullable=False, server_default="0.00"
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
            name=op.f("fk_contrato_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_contrato_obra_id_obra"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["terceros.tercero.id"],
            name=op.f("fk_contrato_cliente_id_tercero"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["terceros.tercero.id"],
            name=op.f("fk_contrato_proveedor_id_tercero"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_contrato_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contrato")),
        sa.UniqueConstraint("organization_id", "codigo", name="contrato_codigo_unique"),
        schema="contratos",
    )
    op.create_index(
        op.f("ix_contratos_contrato_organization_id"), "contrato",
        ["organization_id"], schema="contratos",
    )
    op.create_index("ix_contratos_contrato_obra", "contrato", ["obra_id"], schema="contratos")
    op.create_index("ix_contratos_contrato_cliente", "contrato", ["cliente_id"], schema="contratos")
    op.create_index(
        "ix_contratos_contrato_proveedor", "contrato", ["proveedor_id"], schema="contratos"
    )

    activar_rls("contratos", "contrato")
    conceder_privilegios_app("contratos")


def downgrade() -> None:
    revocar_privilegios_app("contratos")
    desactivar_rls("contratos", "contrato")
    op.drop_table("contrato", schema="contratos")
    op.execute("DROP SCHEMA IF EXISTS contratos CASCADE")
