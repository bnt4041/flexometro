"""obras: desde cuándo la obra está en su estado actual

Hace falta para poder avisar de obras estancadas («lleva 3 meses sin cambiar
de estado»). `updated_at` no sirve: cambia al tocar cualquier campo, así que
una obra parada a la que se le corrige el teléfono parecería recién movida.

Las filas existentes arrancan con su `updated_at`, que es lo más cercano que
se puede saber hoy — nadie guardó cuándo cambió de estado de verdad. Es una
aproximación, y hay que contar con que la primera pasada de la vigilancia
señale obras cuyo `updated_at` sea antiguo por otro motivo.

Revision ID: obras_0008
Revises: obras_0007
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "obras_0008"
down_revision: str | None = "obras_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "obra",
        sa.Column(
            "estado_desde", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        schema="obras",
    )
    op.execute("UPDATE obras.obra SET estado_desde = updated_at")


def downgrade() -> None:
    op.drop_column("obra", "estado_desde", schema="obras")
