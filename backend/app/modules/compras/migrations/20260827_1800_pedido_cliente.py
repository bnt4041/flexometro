"""compras: pedido admite tipo cliente

Un pedido puede ser a proveedor (como hasta ahora) o de cliente — mismo
objeto con `tipo`, igual que ya hace `contratos.Contrato`. `proveedor_id`
pasa a ser opcional (uno de los dos, según `tipo`, validado en el schema) y
se añade `cliente_id`.

Los pedidos existentes (ninguno todavía en producción a fecha de esta
migración) se quedan con `tipo='proveedor'`, que es lo único que podían ser
hasta ahora.

Revision ID: compras_0010
Revises: compras_0009
Create Date: 2026-08-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "compras_0010"
down_revision: str | None = "compras_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pedido",
        sa.Column(
            "tipo",
            sa.Enum("cliente", "proveedor", name="tipo_pedido", native_enum=False, length=32),
            nullable=False,
            server_default="proveedor",
        ),
        schema="compras",
    )
    op.alter_column("pedido", "proveedor_id", nullable=True, schema="compras")
    op.add_column(
        "pedido", sa.Column("cliente_id", sa.UUID(), nullable=True), schema="compras"
    )
    op.create_foreign_key(
        op.f("fk_pedido_cliente_id_tercero"), "pedido", "tercero",
        ["cliente_id"], ["id"], source_schema="compras", referent_schema="terceros",
        ondelete="RESTRICT",
    )
    op.create_index("ix_compras_pedido_cliente", "pedido", ["cliente_id"], schema="compras")


def downgrade() -> None:
    op.drop_index("ix_compras_pedido_cliente", table_name="pedido", schema="compras")
    op.drop_constraint(
        op.f("fk_pedido_cliente_id_tercero"), "pedido", schema="compras", type_="foreignkey"
    )
    op.drop_column("pedido", "cliente_id", schema="compras")
    op.alter_column("pedido", "proveedor_id", nullable=False, schema="compras")
    op.drop_column("pedido", "tipo", schema="compras")
