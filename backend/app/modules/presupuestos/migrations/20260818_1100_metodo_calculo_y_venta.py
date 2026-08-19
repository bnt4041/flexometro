"""metodo de calculo y precio de venta

Revision ID: presupuestos_0008
Revises: presupuestos_0007
Create Date: 2026-08-18 11:00:00

Fase 35: el presupuesto elige cómo pasa del coste a la venta (clásico
PEM+%GG+%BI, incremento sobre el coste, o beneficio final sobre la venta), y
cada partida guarda su precio de venta, que puede bloquearse con un candado
para que un reajuste de porcentajes no lo mueva.

Los valores por defecto dejan el comportamiento anterior intacto: método
clásico y venta calculada, que es exactamente lo que hacía la aplicación.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "presupuestos_0008"
down_revision: str | None = "presupuestos_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "presupuesto",
        sa.Column(
            "metodo_calculo",
            sa.Enum(
                "clasico", "incremento_sobre_coste", "beneficio_final",
                name="metodo_calculo", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="clasico",
        ),
        schema="presupuestos",
    )
    op.add_column(
        "presupuesto",
        sa.Column(
            "porcentaje_metodo", sa.Numeric(precision=5, scale=2),
            nullable=False, server_default="0",
        ),
        schema="presupuestos",
    )

    op.add_column(
        "partida",
        sa.Column(
            "precio_venta", sa.Numeric(precision=14, scale=2),
            nullable=False, server_default="0",
        ),
        schema="presupuestos",
    )
    op.add_column(
        "partida",
        sa.Column(
            "venta_bloqueada", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        schema="presupuestos",
    )
    op.add_column(
        "partida",
        sa.Column(
            "importe_venta", sa.Numeric(precision=16, scale=2),
            nullable=False, server_default="0",
        ),
        schema="presupuestos",
    )

    # Las partidas que ya existen arrancan con la venta del método clásico
    # (coste + %GG + %BI del presupuesto), que es el importe que esos
    # presupuestos ya venían enseñando. Dejarlas a cero haría aparecer todo a
    # pérdida en cuanto se abriera la pantalla.
    op.execute(
        """
        UPDATE presupuestos.partida p
        SET precio_venta = ROUND(
                p.precio * (1 + (pr.gastos_generales + pr.beneficio_industrial) / 100), 2
            ),
            importe_venta = ROUND(
                p.medicion * ROUND(
                    p.precio * (1 + (pr.gastos_generales + pr.beneficio_industrial) / 100), 2
                ), 2
            )
        FROM presupuestos.presupuesto pr
        WHERE pr.id = p.presupuesto_id
        """
    )


def downgrade() -> None:
    op.drop_column("partida", "importe_venta", schema="presupuestos")
    op.drop_column("partida", "venta_bloqueada", schema="presupuestos")
    op.drop_column("partida", "precio_venta", schema="presupuestos")
    op.drop_column("presupuesto", "porcentaje_metodo", schema="presupuestos")
    op.drop_column("presupuesto", "metodo_calculo", schema="presupuestos")
