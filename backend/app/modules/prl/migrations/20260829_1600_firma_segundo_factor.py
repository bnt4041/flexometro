"""prl: segundo factor, sello e integridad en la firma

Tres cosas que suben el nivel de la evidencia:

1. **Código de un solo uso.** Un enlace por correo demuestra, como mucho, que
   quien firma tuvo acceso a ese correo en algún momento — y los enlaces se
   reenvían. Pedir además un código al firmar demuestra que controla esa
   cuenta EN ESE momento. Se guarda el HASH del código, nunca el código: con
   el claro en la tabla, cualquiera con acceso a la base de datos podría
   firmar por el destinatario.

2. **Hash del documento firmado.** SHA-256 de lo que se firmó, para poder
   demostrar después que un PDF dado es ese y no otro.

3. **Posiciones de firma.** Dónde colocó el emisor cada firma sobre el PDF,
   en fracciones del tamaño de página (no en puntos) para no depender de la
   resolución con la que se pintara el visor.

Revision ID: prl_0003
Revises: prl_0002
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "prl_0003"
down_revision: str | None = "prl_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for nombre, tipo in [
        ("otp_hash", sa.String(length=64)),
        ("otp_expira_en", sa.DateTime(timezone=True)),
        ("otp_verificado_en", sa.DateTime(timezone=True)),
        ("hash_documento", sa.String(length=64)),
    ]:
        op.add_column("solicitud_firma", sa.Column(nombre, tipo, nullable=True), schema="prl")

    op.add_column(
        "solicitud_firma",
        sa.Column("otp_intentos", sa.Integer(), nullable=False, server_default="0"),
        schema="prl",
    )
    op.add_column(
        "solicitud_firma",
        sa.Column("posiciones_firma", postgresql.JSONB(), nullable=True),
        schema="prl",
    )


def downgrade() -> None:
    for nombre in (
        "posiciones_firma",
        "otp_intentos",
        "hash_documento",
        "otp_verificado_en",
        "otp_expira_en",
        "otp_hash",
    ):
        op.drop_column("solicitud_firma", nombre, schema="prl")
