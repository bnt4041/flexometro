"""compras: albarán admite tipo cliente

Un albarán puede ser de proveedor (material recibido, como hasta ahora) o
de cliente (lo entregado/ejecutado que se le hace llegar) — mismo objeto con
`tipo`, igual que ya hacen `Pedido` y `contratos.Contrato`. `proveedor_id`
pasa a ser opcional (uno de los dos, según `tipo`, validado en el schema) y
se añade `cliente_id`.

Los albaranes existentes se quedan con `tipo='proveedor'`, que es lo único
que podían ser hasta ahora.

Revision ID: compras_0011
Revises: compras_0010
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "compras_0011"
down_revision: str | None = "compras_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "albaran",
        sa.Column(
            "tipo",
            sa.Enum("cliente", "proveedor", name="tipo_albaran", native_enum=False, length=32),
            nullable=False,
            server_default="proveedor",
        ),
        schema="compras",
    )
    op.alter_column("albaran", "proveedor_id", nullable=True, schema="compras")
    op.add_column(
        "albaran", sa.Column("cliente_id", sa.UUID(), nullable=True), schema="compras"
    )
    op.create_foreign_key(
        op.f("fk_albaran_cliente_id_tercero"), "albaran", "tercero",
        ["cliente_id"], ["id"], source_schema="compras", referent_schema="terceros",
        ondelete="RESTRICT",
    )
    op.create_index("ix_compras_albaran_cliente", "albaran", ["cliente_id"], schema="compras")


def downgrade() -> None:
    op.drop_index("ix_compras_albaran_cliente", table_name="albaran", schema="compras")
    op.drop_constraint(
        op.f("fk_albaran_cliente_id_tercero"), "albaran", schema="compras", type_="foreignkey"
    )
    op.drop_column("albaran", "cliente_id", schema="compras")
    op.alter_column("albaran", "proveedor_id", nullable=False, schema="compras")
    op.drop_column("albaran", "tipo", schema="compras")
