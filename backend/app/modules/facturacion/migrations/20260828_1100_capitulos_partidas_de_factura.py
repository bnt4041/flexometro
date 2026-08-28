"""facturacion: capítulos, partidas y mediciones de factura

Fase 1 de la jerarquía capítulo/partida/medición en Pedidos y Facturas (ver
docstring de `Factura` en `models.py`, y `compras_0012`/`compras_0013` para
el mismo cambio en `Pedido`/`FacturaRecibida`). `Factura` nace sin ninguna
línea hasta ahora — solo `base_imponible`/`total` a mano — y gana la misma
estructura de tres niveles que `Presupuesto`
(`Capitulo`/`Partida`/`LineaMedicion` en `presupuestos.models_presupuesto`),
con su cuarta tabla de descomposición propia (`FacturaPartidaDescomposicion`)
siempre disponible: una factura de venta es siempre de cliente.

`facturacion.factura` tiene exactamente 1 fila en producción (código
FAC00001, dato verificado antes de escribir esta migración) con
`base_imponible`/`total` puestos a mano. Esta migración no la toca: las
columnas nuevas en `factura` llevan `server_default`, y las tablas nuevas
nacen vacías — el recálculo de `base_imponible`/`total` desde las partidas es
trabajo de servicio (Fase 2), no de esta migración.

Revision ID: facturacion_0004
Revises: facturacion_0003
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, desactivar_rls

revision: str = "facturacion_0004"
down_revision: str | None = "facturacion_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "factura",
        sa.Column(
            "metodo_calculo",
            sa.Enum(
                "clasico", "incremento_sobre_coste", "beneficio_final",
                name="metodo_calculo", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="clasico",
        ),
        schema="facturacion",
    )
    op.add_column(
        "factura",
        sa.Column(
            "porcentaje_metodo", sa.Numeric(precision=5, scale=2),
            nullable=False, server_default="0",
        ),
        schema="facturacion",
    )

    op.create_table(
        "factura_capitulo",
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
            name=op.f("fk_factura_capitulo_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["factura_id"], ["facturacion.factura.id"],
            name=op.f("fk_factura_capitulo_factura_id_factura"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_capitulo")),
        schema="facturacion",
    )
    op.create_index(
        op.f("ix_facturacion_factura_capitulo_organization_id"),
        "factura_capitulo", ["organization_id"], schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_capitulo_factura",
        "factura_capitulo", ["factura_id"], schema="facturacion",
    )

    op.create_table(
        "factura_partida",
        sa.Column("factura_id", sa.UUID(), nullable=False),
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
            ["capitulo_id"], ["facturacion.factura_capitulo.id"],
            name=op.f("fk_factura_partida_capitulo_id_factura_capitulo"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["concepto_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_factura_partida_concepto_id_concepto"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_factura_partida_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["factura_id"], ["facturacion.factura.id"],
            name=op.f("fk_factura_partida_factura_id_factura"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_partida")),
        schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_partida_capitulo",
        "factura_partida", ["capitulo_id"], schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_partida_factura",
        "factura_partida", ["factura_id"], schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_partida_concepto",
        "factura_partida", ["concepto_id"], schema="facturacion",
    )
    op.create_index(
        op.f("ix_facturacion_factura_partida_organization_id"),
        "factura_partida", ["organization_id"], schema="facturacion",
    )

    op.create_table(
        "factura_medicion",
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
            name=op.f("fk_factura_medicion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["facturacion.factura_partida.id"],
            name=op.f("fk_factura_medicion_partida_id_factura_partida"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_medicion")),
        schema="facturacion",
    )
    op.create_index(
        op.f("ix_facturacion_factura_medicion_organization_id"),
        "factura_medicion", ["organization_id"], schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_medicion_partida",
        "factura_medicion", ["partida_id"], schema="facturacion",
    )

    op.create_table(
        "factura_partida_descomposicion",
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
            name=op.f("fk_factura_partida_descomposicion_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["facturacion.factura_partida.id"],
            name=op.f("fk_factura_partida_descomposicion_partida_id_factura_partida"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hijo_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_factura_partida_descomposicion_hijo_id_concepto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_factura_partida_descomposicion")),
        schema="facturacion",
    )
    op.create_index(
        op.f("ix_facturacion_factura_partida_descomposicion_organization_id"),
        "factura_partida_descomposicion", ["organization_id"], schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_partida_descomposicion_partida",
        "factura_partida_descomposicion", ["partida_id"], schema="facturacion",
    )
    op.create_index(
        "ix_facturacion_factura_partida_descomposicion_hijo",
        "factura_partida_descomposicion", ["hijo_id"], schema="facturacion",
    )

    for tabla in (
        "factura_capitulo", "factura_partida", "factura_medicion", "factura_partida_descomposicion",
    ):
        activar_rls("facturacion", tabla)


def downgrade() -> None:
    for tabla in (
        "factura_partida_descomposicion", "factura_medicion", "factura_partida", "factura_capitulo",
    ):
        desactivar_rls("facturacion", tabla)

    op.drop_index(
        "ix_facturacion_factura_partida_descomposicion_hijo",
        table_name="factura_partida_descomposicion", schema="facturacion",
    )
    op.drop_index(
        "ix_facturacion_factura_partida_descomposicion_partida",
        table_name="factura_partida_descomposicion", schema="facturacion",
    )
    op.drop_index(
        op.f("ix_facturacion_factura_partida_descomposicion_organization_id"),
        table_name="factura_partida_descomposicion", schema="facturacion",
    )
    op.drop_table("factura_partida_descomposicion", schema="facturacion")

    op.drop_index(
        "ix_facturacion_factura_medicion_partida",
        table_name="factura_medicion", schema="facturacion",
    )
    op.drop_index(
        op.f("ix_facturacion_factura_medicion_organization_id"),
        table_name="factura_medicion", schema="facturacion",
    )
    op.drop_table("factura_medicion", schema="facturacion")

    op.drop_index(
        op.f("ix_facturacion_factura_partida_organization_id"),
        table_name="factura_partida", schema="facturacion",
    )
    op.drop_index(
        "ix_facturacion_factura_partida_concepto",
        table_name="factura_partida", schema="facturacion",
    )
    op.drop_index(
        "ix_facturacion_factura_partida_factura",
        table_name="factura_partida", schema="facturacion",
    )
    op.drop_index(
        "ix_facturacion_factura_partida_capitulo",
        table_name="factura_partida", schema="facturacion",
    )
    op.drop_table("factura_partida", schema="facturacion")

    op.drop_index(
        "ix_facturacion_factura_capitulo_factura",
        table_name="factura_capitulo", schema="facturacion",
    )
    op.drop_index(
        op.f("ix_facturacion_factura_capitulo_organization_id"),
        table_name="factura_capitulo", schema="facturacion",
    )
    op.drop_table("factura_capitulo", schema="facturacion")

    op.drop_column("factura", "porcentaje_metodo", schema="facturacion")
    op.drop_column("factura", "metodo_calculo", schema="facturacion")
