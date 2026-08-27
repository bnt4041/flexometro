"""core: puente para devolver la oferta a quien la pidió

Cuando un proveedor con Flexómetro acepta una solicitud, se le crea un
presupuesto suyo. Faltaba el camino de vuelta: poder mandárselo al emisor para
que entre en su comparativo.

`mapa_lineas` guarda qué partida suya corresponde a qué línea de la solicitud
del emisor. Va en la notificación —en la organización del proveedor— y no como
FK, porque una clave ajena entre dos organizaciones distintas no tendría
sentido: son documentos de empresas diferentes, cada una con su CIF.

Revision ID: core_notif_0002
Revises: core_notif_0001
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "core_notif_0002"
down_revision: str | None = "core_notif_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notificacion",
        sa.Column(
            "mapa_lineas", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        schema="core",
    )
    op.add_column(
        "notificacion",
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("notificacion", "enviada_en", schema="core")
    op.drop_column("notificacion", "mapa_lineas", schema="core")
