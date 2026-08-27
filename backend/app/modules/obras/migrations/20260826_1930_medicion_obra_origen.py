"""obras: de qué parcial del presupuesto salió cada medición de obra

`medicion_obra.origen_linea_id` a NULL significa «esto se midió en obra». Es lo
que permite negarse a desvincular un anexo sobre el que ya se ha trabajado.

Se añade aparte y no dentro de `obras_0004` porque esa ya está aplicada:
reescribir una migración publicada obliga a un downgrade sobre datos vivos, y
no merece la pena por una columna.

El intento anterior era comparar `created_at` de la medición con el de la
partida. No funciona: `now()` en PostgreSQL devuelve la hora de la
TRANSACCIÓN, así que copiar el árbol y medir en la misma petición dejan el
mismo sello y la comparación sale siempre falsa.

Revision ID: obras_0005
Revises: obras_0004
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "obras_0005"
down_revision: str | None = "obras_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medicion_obra",
        sa.Column("origen_linea_id", sa.UUID(), nullable=True),
        schema="obras",
    )
    op.create_foreign_key(
        op.f("fk_medicion_obra_origen_linea_id_linea_medicion"),
        "medicion_obra",
        "linea_medicion",
        ["origen_linea_id"],
        ["id"],
        source_schema="obras",
        referent_schema="presupuestos",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_medicion_obra_origen_linea_id_linea_medicion"),
        "medicion_obra",
        schema="obras",
        type_="foreignkey",
    )
    op.drop_column("medicion_obra", "origen_linea_id", schema="obras")
