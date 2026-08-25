"""compras: pedir precio de un componente y mandarlo a otro correo

Dos añadidos a la solicitud de precios:

- `solicitud_linea.concepto_id`: cuando viene relleno, la línea no pide la
  partida entera sino UN componente de su descompuesto (solo la mano de obra,
  solo el material, un telefonillo concreto). Se identifica por
  (partida, concepto) y no por la fila del descompuesto porque mientras la
  partida hereda del banco esas filas pertenecen al concepto padre y su id
  cambia en cuanto se independiza: no sirve como referencia estable.
- `solicitud_precios.email_destino`: a quién mandarle la separata cuando no
  es el correo de la ficha del proveedor. No toca la ficha del tercero.

Revision ID: compras_0004
Revises: compras_0003
Create Date: 2026-08-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "compras_0004"
down_revision: str | None = "compras_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "solicitud_linea",
        sa.Column("concepto_id", sa.UUID(), nullable=True),
        schema="compras",
    )
    op.create_foreign_key(
        op.f("fk_solicitud_linea_concepto_id_concepto"),
        "solicitud_linea",
        "concepto",
        ["concepto_id"],
        ["id"],
        source_schema="compras",
        referent_schema="presupuestos",
        ondelete="SET NULL",
    )
    op.add_column(
        "solicitud_precios",
        sa.Column("email_destino", sa.String(length=200), nullable=True),
        schema="compras",
    )


def downgrade() -> None:
    op.drop_column("solicitud_precios", "email_destino", schema="compras")
    op.drop_constraint(
        op.f("fk_solicitud_linea_concepto_id_concepto"),
        "solicitud_linea",
        schema="compras",
        type_="foreignkey",
    )
    op.drop_column("solicitud_linea", "concepto_id", schema="compras")
