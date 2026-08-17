"""contacto asociado

Revision ID: terceros_0003
Revises: 5eef0f540e95
Create Date: 2026-08-16 10:30:00

Fase 28: `contacto_asociado` vincula un `Contacto` con cualquier otro
registro del negocio (presupuesto, obra, certificación, factura...), N a N.
`entidad`/`entidad_id` sueltos (sin FK por tabla), mismo patrón que
`campos_libres.valor` — ver el docstring de `ContactoAsociado` en
`terceros/models.py`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, desactivar_rls

revision: str = "terceros_0003"
down_revision: str | None = "5eef0f540e95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contacto_asociado",
        sa.Column(
            "entidad",
            sa.Enum(
                "presupuesto", "obra", "certificacion", "factura",
                name="entidad_contacto", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("entidad_id", sa.UUID(), nullable=False),
        sa.Column("contacto_id", sa.UUID(), nullable=False),
        sa.Column("rol", sa.String(length=80), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_contacto_asociado_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contacto_id"],
            ["terceros.contacto.id"],
            name=op.f("fk_contacto_asociado_contacto_id_contacto"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacto_asociado")),
        sa.UniqueConstraint(
            "organization_id", "entidad", "entidad_id", "contacto_id",
            name="contacto_asociado_unique",
        ),
        schema="terceros",
    )
    op.create_index(
        op.f("ix_terceros_contacto_asociado_organization_id"),
        "contacto_asociado", ["organization_id"], unique=False, schema="terceros",
    )
    op.create_index(
        op.f("ix_terceros_contacto_asociado_contacto_id"),
        "contacto_asociado", ["contacto_id"], unique=False, schema="terceros",
    )
    op.create_index(
        "ix_terceros_contacto_asociado_entidad",
        "contacto_asociado", ["organization_id", "entidad", "entidad_id"],
        unique=False, schema="terceros",
    )

    activar_rls("terceros", "contacto_asociado")


def downgrade() -> None:
    desactivar_rls("terceros", "contacto_asociado")

    op.drop_index(
        "ix_terceros_contacto_asociado_entidad", table_name="contacto_asociado", schema="terceros",
    )
    op.drop_index(
        op.f("ix_terceros_contacto_asociado_contacto_id"), table_name="contacto_asociado", schema="terceros",
    )
    op.drop_index(
        op.f("ix_terceros_contacto_asociado_organization_id"), table_name="contacto_asociado", schema="terceros",
    )
    op.drop_table("contacto_asociado", schema="terceros")
