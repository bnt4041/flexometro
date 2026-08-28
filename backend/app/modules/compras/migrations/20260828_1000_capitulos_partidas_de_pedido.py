"""compras: capítulos, partidas y mediciones de pedido

Fase 1 de la jerarquía capítulo/partida/medición en Pedidos y Facturas (ver
docstring de `Pedido` en `models.py`): la línea plana `PedidoLinea` se
sustituye por la misma estructura de tres niveles que ya usa `Presupuesto`
(`Capitulo`/`Partida`/`LineaMedicion` en `models_presupuesto.py`), con una
cuarta tabla de descomposición propia (`PedidoPartidaDescomposicion`) que
solo se rellena de verdad en pedidos de cliente — en los de proveedor la
partida es siempre alzada, y eso lo impone el servicio (Fase 2), no la base
de datos.

Se puede tirar `pedido_linea` sin conversión: a fecha de esta migración
`compras.pedido`/`compras.pedido_linea` tienen 0 filas en producción (dato
verificado antes de escribir esta migración), así que no hay nada que
preservar.

Revision ID: compras_0012
Revises: compras_0011
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, desactivar_rls

revision: str = "compras_0012"
down_revision: str | None = "compras_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Pedido gana método de cálculo (solo aplicable en tipo=cliente) ---
    op.add_column(
        "pedido",
        sa.Column(
            "metodo_calculo",
            sa.Enum(
                "clasico", "incremento_sobre_coste", "beneficio_final",
                name="metodo_calculo", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="clasico",
        ),
        schema="compras",
    )
    op.add_column(
        "pedido",
        sa.Column(
            "porcentaje_metodo", sa.Numeric(precision=5, scale=2),
            nullable=False, server_default="0",
        ),
        schema="compras",
    )

    # --- Se retira la línea plana: 0 filas reales, nada que convertir ---
    op.drop_index(
        "ix_compras_pedido_linea_pedido", table_name="pedido_linea", schema="compras"
    )
    desactivar_rls("compras", "pedido_linea")
    op.drop_table("pedido_linea", schema="compras")

    # --- Capítulo (plano, sin parent_id) ---
    op.create_table(
        "pedido_capitulo",
        sa.Column("pedido_id", sa.UUID(), nullable=False),
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
            name=op.f("fk_pedido_capitulo_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"], ["compras.pedido.id"],
            name=op.f("fk_pedido_capitulo_pedido_id_pedido"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_capitulo")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_pedido_capitulo_organization_id"),
        "pedido_capitulo", ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_pedido_capitulo_pedido", "pedido_capitulo", ["pedido_id"], schema="compras"
    )

    # --- Partida ---
    op.create_table(
        "pedido_partida",
        sa.Column("pedido_id", sa.UUID(), nullable=False),
        sa.Column("capitulo_id", sa.UUID(), nullable=False),
        sa.Column("concepto_id", sa.UUID(), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=False, server_default="ud"),
        sa.Column("precio", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("costes_indirectos", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("precio_venta", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("venta_bloqueada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("importe_venta", sa.Numeric(precision=16, scale=2), nullable=False, server_default="0"),
        sa.Column("medicion", sa.Numeric(precision=14, scale=3), nullable=False, server_default="0"),
        sa.Column("importe", sa.Numeric(precision=16, scale=2), nullable=False, server_default="0"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["capitulo_id"], ["compras.pedido_capitulo.id"],
            name=op.f("fk_pedido_partida_capitulo_id_pedido_capitulo"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concepto_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_pedido_partida_concepto_id_concepto"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_pedido_partida_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"], ["compras.pedido.id"],
            name=op.f("fk_pedido_partida_pedido_id_pedido"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_partida")),
        schema="compras",
    )
    op.create_index(
        "ix_compras_pedido_partida_capitulo", "pedido_partida", ["capitulo_id"], schema="compras"
    )
    op.create_index(
        "ix_compras_pedido_partida_pedido", "pedido_partida", ["pedido_id"], schema="compras"
    )
    op.create_index(
        "ix_compras_pedido_partida_concepto", "pedido_partida", ["concepto_id"], schema="compras"
    )
    op.create_index(
        op.f("ix_compras_pedido_partida_organization_id"),
        "pedido_partida", ["organization_id"], schema="compras",
    )

    # --- Medición ---
    op.create_table(
        "pedido_medicion",
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
            name=op.f("fk_pedido_medicion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["compras.pedido_partida.id"],
            name=op.f("fk_pedido_medicion_partida_id_pedido_partida"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_medicion")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_pedido_medicion_organization_id"),
        "pedido_medicion", ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_pedido_medicion_partida", "pedido_medicion", ["partida_id"], schema="compras"
    )

    # --- Descomposición propia (solo se rellena en pedidos de cliente) ---
    op.create_table(
        "pedido_partida_descomposicion",
        sa.Column("partida_id", sa.UUID(), nullable=False),
        sa.Column("hijo_id", sa.UUID(), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("unidad", sa.String(length=10), nullable=False, server_default="ud"),
        sa.Column("naturaleza", sa.String(length=32), nullable=True),
        sa.Column("rendimiento", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("factor", sa.Numeric(precision=14, scale=6), nullable=False, server_default="1"),
        sa.Column("precio", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0"),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_pedido_partida_descomposicion_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["compras.pedido_partida.id"],
            name=op.f("fk_pedido_partida_descomposicion_partida_id_pedido_partida"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hijo_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_pedido_partida_descomposicion_hijo_id_concepto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_partida_descomposicion")),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_pedido_partida_descomposicion_organization_id"),
        "pedido_partida_descomposicion", ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_pedido_partida_descomposicion_partida",
        "pedido_partida_descomposicion", ["partida_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_pedido_partida_descomposicion_hijo",
        "pedido_partida_descomposicion", ["hijo_id"], schema="compras",
    )

    for tabla in ("pedido_capitulo", "pedido_partida", "pedido_medicion", "pedido_partida_descomposicion"):
        activar_rls("compras", tabla)


def downgrade() -> None:
    for tabla in (
        "pedido_partida_descomposicion", "pedido_medicion", "pedido_partida", "pedido_capitulo",
    ):
        desactivar_rls("compras", tabla)

    op.drop_index(
        "ix_compras_pedido_partida_descomposicion_hijo",
        table_name="pedido_partida_descomposicion", schema="compras",
    )
    op.drop_index(
        "ix_compras_pedido_partida_descomposicion_partida",
        table_name="pedido_partida_descomposicion", schema="compras",
    )
    op.drop_index(
        op.f("ix_compras_pedido_partida_descomposicion_organization_id"),
        table_name="pedido_partida_descomposicion", schema="compras",
    )
    op.drop_table("pedido_partida_descomposicion", schema="compras")

    op.drop_index(
        "ix_compras_pedido_medicion_partida", table_name="pedido_medicion", schema="compras"
    )
    op.drop_index(
        op.f("ix_compras_pedido_medicion_organization_id"),
        table_name="pedido_medicion", schema="compras",
    )
    op.drop_table("pedido_medicion", schema="compras")

    op.drop_index(
        op.f("ix_compras_pedido_partida_organization_id"),
        table_name="pedido_partida", schema="compras",
    )
    op.drop_index(
        "ix_compras_pedido_partida_concepto", table_name="pedido_partida", schema="compras"
    )
    op.drop_index(
        "ix_compras_pedido_partida_pedido", table_name="pedido_partida", schema="compras"
    )
    op.drop_index(
        "ix_compras_pedido_partida_capitulo", table_name="pedido_partida", schema="compras"
    )
    op.drop_table("pedido_partida", schema="compras")

    op.drop_index(
        "ix_compras_pedido_capitulo_pedido", table_name="pedido_capitulo", schema="compras"
    )
    op.drop_index(
        op.f("ix_compras_pedido_capitulo_organization_id"),
        table_name="pedido_capitulo", schema="compras",
    )
    op.drop_table("pedido_capitulo", schema="compras")

    # --- Se recrea `pedido_linea` con su forma original, por simetría ---
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
    activar_rls("compras", "pedido_linea")

    op.drop_column("pedido", "porcentaje_metodo", schema="compras")
    op.drop_column("pedido", "metodo_calculo", schema="compras")
