"""compras: el proveedor puede desglosar su precio

Mismo paradigma que el descompuesto de una partida —código, descripción,
unidad, naturaleza, rendimiento, factor y precio— pero SIN referencia al banco
de precios: el banco es del emisor, y dar de alta conceptos desde la separata
lo llenaría de fichas de sus proveedores. Todo va como texto congelado.

Si una línea tiene descompuesto, su precio ofertado pasa a ser la suma de
(rendimiento x factor x precio), igual que una partida con descompuesto propio.

Revision ID: compras_0007
Revises: compras_0006
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "compras_0007"
down_revision: str | None = "compras_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oferta_descompuesto",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("oferta_linea_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=True),
        sa.Column("resumen", sa.String(length=250), nullable=False, server_default=""),
        sa.Column("unidad", sa.String(length=10), nullable=False, server_default="ud"),
        sa.Column("naturaleza", sa.String(length=32), nullable=True),
        sa.Column(
            "rendimiento", sa.Numeric(precision=14, scale=6), nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "factor", sa.Numeric(precision=14, scale=6), nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "precio", sa.Numeric(precision=14, scale=2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_oferta_descompuesto_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_linea_id"], ["compras.oferta_linea.id"],
            name=op.f("fk_oferta_descompuesto_oferta_linea_id_oferta_linea"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oferta_descompuesto")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_oferta_descompuesto_organization_id"), "oferta_descompuesto",
        ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_oferta_descompuesto_oferta", "oferta_descompuesto",
        ["oferta_linea_id"], schema="compras",
    )

    activar_rls("compras", "oferta_descompuesto")
    conceder_privilegios_app("compras")


def downgrade() -> None:
    desactivar_rls("compras", "oferta_descompuesto")
    op.drop_table("oferta_descompuesto", schema="compras")
