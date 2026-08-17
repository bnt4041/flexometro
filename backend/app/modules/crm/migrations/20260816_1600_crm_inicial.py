"""crm inicial

Revision ID: crm_0001
Revises:
Create Date: 2026-08-16 16:00:00

Fase 29: `nota`, un cuaderno de bitácora por organización sobre cualquier
objeto grande del negocio (tercero, presupuesto, obra, certificación,
factura). `entidad`/`entidad_id` sueltos, mismo patrón que
`campos_libres.valor` — ver el docstring de `crm/models.py`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "crm_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("crm",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS crm")

    op.create_table(
        "nota",
        sa.Column(
            "entidad",
            sa.Enum(
                "tercero", "presupuesto", "obra", "certificacion", "factura",
                name="entidad_nota", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("entidad_id", sa.UUID(), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_nota_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nota")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_crm_nota_organization_id"),
        "nota", ["organization_id"], unique=False, schema="crm",
    )
    op.create_index(
        "ix_crm_nota_entidad",
        "nota", ["organization_id", "entidad", "entidad_id"], unique=False, schema="crm",
    )

    activar_rls("crm", "nota")

    # Schema nuevo: sin esto el rol de mínimo privilegio no tiene ni USAGE
    # sobre él (lección de la Fase 7).
    conceder_privilegios_app("crm")


def downgrade() -> None:
    revocar_privilegios_app("crm")
    desactivar_rls("crm", "nota")

    op.drop_index("ix_crm_nota_entidad", table_name="nota", schema="crm")
    op.drop_index(op.f("ix_crm_nota_organization_id"), table_name="nota", schema="crm")
    op.drop_table("nota", schema="crm")
    op.execute("DROP SCHEMA IF EXISTS crm CASCADE")
