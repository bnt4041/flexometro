"""planos: marcar lo que ha dibujado la IA sobre el plano

Revision ID: pln_0003
Revises: pln_0002
Create Date: 2026-09-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "pln_0003"
down_revision: str | None = "pln_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "planos"


def upgrade() -> None:
    # Una marca y no una capa aparte: lo que propone la IA se mueve, se ajusta
    # y acaba siendo una medición normal, así que tiene que poder vivir en la
    # capa que le corresponda. Lo que no puede es pasar por medido sin que se
    # note: su geometría es aproximada hasta que alguien la revisa.
    op.add_column(
        "elemento_plano",
        sa.Column(
            "propuesto_ia", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("elemento_plano", "propuesto_ia", schema=SCHEMA)
