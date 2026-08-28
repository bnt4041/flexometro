"""compras: capítulos, partidas y mediciones de factura recibida

Fase 1 de la jerarquía capítulo/partida/medición (ver `compras_0012` para el
mismo cambio en `Pedido`, y el docstring de `FacturaRecibida` en
`models.py`). `FacturaRecibida` nace sin ninguna línea hasta ahora — solo un
importe a mano — y gana la misma estructura de tres niveles que `Presupuesto`
(`Capitulo`/`Partida`/`LineaMedicion`), **sin tabla de descomposición**: una
factura recibida es siempre de proveedor, así que la partida es siempre
alzada, precio directo, y ese cuarto nivel no aplica aquí (a diferencia de
`Pedido`/`Factura`, que sí lo llevan).

`compras.factura_recibida` tiene 1 fila en producción (dato verificado antes
de escribir esta migración) pero esta migración no la toca: solo crea tablas
nuevas y vacías.

Revision ID: compras_0013
Revises: compras_0012
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, desactivar_rls

revision: str = "compras_0013"
down_revision: str | None = "compras_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "factura_recibida_capitulo",
        sa.Column("factura_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_factura_recibida_capitulo_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["factura_id"], ["compras.factura_recibida.id"],
            name=op.f("fk_factura_recibida_capitulo_factura_id_factura_recibida"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_recibida_capitulo")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_factura_recibida_capitulo_organization_id"),
        "factura_recibida_capitulo", ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_capitulo_factura",
        "factura_recibida_capitulo", ["factura_id"], schema="compras",
    )

    op.create_table(
        "factura_recibida_partida",
        sa.Column("factura_id", sa.UUID(), nullable=False),
        sa.Column("capitulo_id", sa.UUID(), nullable=False),
        sa.Column("concepto_id", sa.UUID(), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=False, server_default="ud"),
        sa.Column("precio", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("medicion", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"),
        sa.Column("importe", sa.Numeric(precision=16, scale=2), nullable=False, server_default="0"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["capitulo_id"], ["compras.factura_recibida_capitulo.id"],
            name=op.f("fk_factura_recibida_partida_capitulo_id_factura_recibida_capitulo"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concepto_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_factura_recibida_partida_concepto_id_concepto"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_factura_recibida_partida_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["factura_id"], ["compras.factura_recibida.id"],
            name=op.f("fk_factura_recibida_partida_factura_id_factura_recibida"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_recibida_partida")),
        schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_partida_capitulo",
        "factura_recibida_partida", ["capitulo_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_partida_factura",
        "factura_recibida_partida", ["factura_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_partida_concepto",
        "factura_recibida_partida", ["concepto_id"], schema="compras",
    )
    op.create_index(
        op.f("ix_compras_factura_recibida_partida_organization_id"),
        "factura_recibida_partida", ["organization_id"], schema="compras",
    )

    op.create_table(
        "factura_recibida_medicion",
        sa.Column("partida_id", sa.UUID(), nullable=False),
        sa.Column("comentario", sa.String(length=250), nullable=True),
        sa.Column("uds", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("longitud", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("anchura", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("altura", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("parcial", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_factura_recibida_medicion_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["compras.factura_recibida_partida.id"],
            name=op.f("fk_factura_recibida_medicion_partida_id_factura_recibida_partida"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_recibida_medicion")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_factura_recibida_medicion_organization_id"),
        "factura_recibida_medicion", ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_factura_recibida_medicion_partida",
        "factura_recibida_medicion", ["partida_id"], schema="compras",
    )

    for tabla in ("factura_recibida_capitulo", "factura_recibida_partida", "factura_recibida_medicion"):
        activar_rls("compras", tabla)


def downgrade() -> None:
    for tabla in ("factura_recibida_medicion", "factura_recibida_partida", "factura_recibida_capitulo"):
        desactivar_rls("compras", tabla)

    op.drop_index(
        "ix_compras_factura_recibida_medicion_partida",
        table_name="factura_recibida_medicion", schema="compras",
    )
    op.drop_index(
        op.f("ix_compras_factura_recibida_medicion_organization_id"),
        table_name="factura_recibida_medicion", schema="compras",
    )
    op.drop_table("factura_recibida_medicion", schema="compras")

    op.drop_index(
        op.f("ix_compras_factura_recibida_partida_organization_id"),
        table_name="factura_recibida_partida", schema="compras",
    )
    op.drop_index(
        "ix_compras_factura_recibida_partida_concepto",
        table_name="factura_recibida_partida", schema="compras",
    )
    op.drop_index(
        "ix_compras_factura_recibida_partida_factura",
        table_name="factura_recibida_partida", schema="compras",
    )
    op.drop_index(
        "ix_compras_factura_recibida_partida_capitulo",
        table_name="factura_recibida_partida", schema="compras",
    )
    op.drop_table("factura_recibida_partida", schema="compras")

    op.drop_index(
        "ix_compras_factura_recibida_capitulo_factura",
        table_name="factura_recibida_capitulo", schema="compras",
    )
    op.drop_index(
        op.f("ix_compras_factura_recibida_capitulo_organization_id"),
        table_name="factura_recibida_capitulo", schema="compras",
    )
    op.drop_table("factura_recibida_capitulo", schema="compras")
