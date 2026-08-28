"""core: modelo de visión de DeepSeek en los ajustes de IA

DeepSeek publica un modelo de visión (`deepseek-v4-flash-vision-exp`) aparte
del de texto, pero servido por la MISMA clave y la misma `base_url` — lo único
que cambia entre una llamada y otra es qué `model` se manda. De ahí que esto
sea una columna más y no un bloque de credenciales nuevo: no hay
`deepseek_vision_api_key` que guardar.

Va con `server_default` porque la columna es NOT NULL y la tabla ya tiene su
fila (es de una sola, `id=1`): sin valor por defecto en el servidor, el
`ALTER TABLE` no podría rellenarla.

Revision ID: core_ia_vision_0001
Revises: core_notif_0002
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "core_ia_vision_0001"
down_revision: str | None = "core_notif_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "configuracion_ia",
        sa.Column(
            "deepseek_vision_model",
            sa.String(60),
            nullable=False,
            server_default=sa.text("'deepseek-v4-flash-vision-exp'"),
        ),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("configuracion_ia", "deepseek_vision_model", schema="core")
