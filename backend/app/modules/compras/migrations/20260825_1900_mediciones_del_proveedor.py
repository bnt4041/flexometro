"""compras: el proveedor puede aportar su propio estado de mediciones

Hasta ahora el proveedor solo podía poner un precio por línea. Con esto puede
justificar su medición como en cualquier presupuesto —comentario, uds, largo,
ancho, alto— y el parcial sale del producto de lo que informe.

Va en tabla propia y no en `presupuestos.linea_medicion` a propósito: es la
medición del PROVEEDOR, que puede no coincidir con la que se le pidió, y no
debe tocar el presupuesto de cliente del emisor. Al cerrar la oferta se
vuelca como líneas de medición de su presupuesto-oferta.

Revision ID: compras_0006
Revises: compras_0005
Create Date: 2026-08-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "compras_0006"
down_revision: str | None = "compras_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oferta_medicion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("oferta_linea_id", sa.UUID(), nullable=False),
        sa.Column("comentario", sa.String(length=250), nullable=True),
        sa.Column("uds", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("longitud", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("anchura", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("altura", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column(
            "parcial", sa.Numeric(precision=14, scale=3), nullable=False,
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
            name=op.f("fk_oferta_medicion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_linea_id"], ["compras.oferta_linea.id"],
            name=op.f("fk_oferta_medicion_oferta_linea_id_oferta_linea"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oferta_medicion")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_oferta_medicion_organization_id"), "oferta_medicion",
        ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_oferta_medicion_oferta", "oferta_medicion",
        ["oferta_linea_id"], schema="compras",
    )

    activar_rls("compras", "oferta_medicion")
    conceder_privilegios_app("compras")


def downgrade() -> None:
    desactivar_rls("compras", "oferta_medicion")
    op.drop_table("oferta_medicion", schema="compras")
