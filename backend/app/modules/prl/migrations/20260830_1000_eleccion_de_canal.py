"""prl: elegir por dónde va el enlace y por dónde el código

Hasta ahora el reparto era automático y no se podía tocar: enlace por
WhatsApp si el firmante tenía móvil, código por el canal contrario. Es un
buen valor por defecto, pero hay documentos que quieren otra cosa — «esto
mándalo por correo, que queda registro» o «mándalo por los dos, que no se
pierda».

`canal_enlace` y `canal_codigo` guardan esa decisión en la SOLICITUD, no en
cada firmante: es una decisión del documento. Arrancan en `auto`, así que
todo lo ya creado sigue comportándose exactamente igual.

`firmante.canal_envio` pasa a `canales_envio` (lista): con la opción «ambos»
un enlace puede salir por dos sitios, y una sola columna no podría contarlo.
Los valores existentes se conservan como listas de un elemento.

Revision ID: prl_0006
Revises: prl_0005
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "prl_0006"
down_revision: str | None = "prl_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREFERENCIA = sa.Enum(
    "auto", "email", "whatsapp", "ambos",
    name="preferencia_canal", native_enum=False, length=32,
)


def upgrade() -> None:
    for columna in ("canal_enlace", "canal_codigo"):
        op.add_column(
            "solicitud_firma",
            sa.Column(columna, _PREFERENCIA, nullable=False, server_default=sa.text("'auto'")),
            schema="prl",
        )

    op.add_column(
        "firmante", sa.Column("canales_envio", postgresql.JSONB(), nullable=True), schema="prl"
    )
    # Lo que ya había, envuelto en una lista de un elemento. NULL se queda
    # NULL: significa «todavía no se le ha mandado nada».
    op.execute(
        """
        UPDATE prl.firmante
        SET canales_envio = to_jsonb(ARRAY[canal_envio])
        WHERE canal_envio IS NOT NULL
        """
    )
    op.drop_column("firmante", "canal_envio", schema="prl")


def downgrade() -> None:
    op.add_column(
        "firmante",
        sa.Column(
            "canal_envio",
            sa.Enum("email", "whatsapp", name="canal_envio", native_enum=False, length=32),
            nullable=True,
        ),
        schema="prl",
    )
    # Con dos canales solo cabe uno: se conserva el primero.
    op.execute(
        """
        UPDATE prl.firmante
        SET canal_envio = canales_envio->>0
        WHERE canales_envio IS NOT NULL AND jsonb_array_length(canales_envio) > 0
        """
    )
    op.drop_column("firmante", "canales_envio", schema="prl")
    op.drop_column("solicitud_firma", "canal_codigo", schema="prl")
    op.drop_column("solicitud_firma", "canal_enlace", schema="prl")
