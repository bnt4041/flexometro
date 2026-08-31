"""prl: teléfono y canal de envío del firmante

Dos columnas para poder mandar la firma por WhatsApp:

- `telefono`: opcional. Sin él, todo sigue yendo por correo exactamente igual
  que antes, así que las solicitudes ya existentes no cambian de
  comportamiento.
- `canal_envio`: por dónde se mandó el enlace. No es solo traza — decide por
  dónde va después el código de verificación, que tiene que ir SIEMPRE por el
  canal contrario. Si enlace y código viajan por el mismo sitio, el segundo
  factor deja de serlo.

Nula en las filas existentes a propósito: de los envíos anteriores a esto no
sabemos el canal con certeza (fue correo, pero afirmarlo en una columna de
evidencia sería inventárselo). El código trata NULL como correo.

Revision ID: prl_0005
Revises: prl_0004
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "prl_0005"
down_revision: str | None = "prl_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "firmante", sa.Column("telefono", sa.String(length=30), nullable=True), schema="prl"
    )
    op.add_column(
        "firmante",
        sa.Column(
            "canal_envio",
            sa.Enum("email", "whatsapp", name="canal_envio", native_enum=False, length=32),
            nullable=True,
        ),
        schema="prl",
    )


def downgrade() -> None:
    op.drop_column("firmante", "canal_envio", schema="prl")
    op.drop_column("firmante", "telefono", schema="prl")
