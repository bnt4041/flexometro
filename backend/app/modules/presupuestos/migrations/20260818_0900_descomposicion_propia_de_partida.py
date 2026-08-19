"""descomposicion propia de partida

Revision ID: presupuestos_0007
Revises: presupuestos_0006
Create Date: 2026-08-18 09:00:00

Fase 34: una partida puede independizarse del banco de precios y llevar su
propio descompuesto, para poder cambiar el precio de un componente "solo
aquí". Ver el docstring de `PartidaDescomposicion` en `models_presupuesto.py`.

`partida.costes_indirectos` acompaña al descompuesto propio: es la copia del
porcentaje que tenía el concepto al independizarse, para que clonar no le
cambie el precio a la partida.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, desactivar_rls

revision: str = "presupuestos_0007"
down_revision: str | None = "presupuestos_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "partida",
        sa.Column("costes_indirectos", sa.Numeric(precision=5, scale=2), nullable=True),
        schema="presupuestos",
    )

    op.create_table(
        "partida_descomposicion",
        sa.Column("partida_id", sa.UUID(), nullable=False),
        sa.Column("hijo_id", sa.UUID(), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("unidad", sa.String(length=10), nullable=False),
        sa.Column("naturaleza", sa.String(length=32), nullable=True),
        sa.Column("rendimiento", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("factor", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("precio", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_partida_descomposicion_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"],
            ["presupuestos.partida.id"],
            name=op.f("fk_partida_descomposicion_partida_id_partida"),
            ondelete="CASCADE",
        ),
        # SET NULL, no RESTRICT: la línea guarda su propia copia del precio,
        # así que perder la referencia al concepto no la deja inservible.
        sa.ForeignKeyConstraint(
            ["hijo_id"],
            ["presupuestos.concepto.id"],
            name=op.f("fk_partida_descomposicion_hijo_id_concepto"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partida_descomposicion")),
        schema="presupuestos",
    )
    op.create_index(
        op.f("ix_presupuestos_partida_descomposicion_organization_id"),
        "partida_descomposicion", ["organization_id"], unique=False, schema="presupuestos",
    )
    op.create_index(
        "ix_presupuestos_partida_descomposicion_partida",
        "partida_descomposicion", ["partida_id"], unique=False, schema="presupuestos",
    )
    op.create_index(
        "ix_presupuestos_partida_descomposicion_hijo",
        "partida_descomposicion", ["hijo_id"], unique=False, schema="presupuestos",
    )

    activar_rls("presupuestos", "partida_descomposicion")


def downgrade() -> None:
    desactivar_rls("presupuestos", "partida_descomposicion")
    op.drop_index(
        "ix_presupuestos_partida_descomposicion_hijo",
        table_name="partida_descomposicion", schema="presupuestos",
    )
    op.drop_index(
        "ix_presupuestos_partida_descomposicion_partida",
        table_name="partida_descomposicion", schema="presupuestos",
    )
    op.drop_index(
        op.f("ix_presupuestos_partida_descomposicion_organization_id"),
        table_name="partida_descomposicion", schema="presupuestos",
    )
    op.drop_table("partida_descomposicion", schema="presupuestos")
    op.drop_column("partida", "costes_indirectos", schema="presupuestos")
