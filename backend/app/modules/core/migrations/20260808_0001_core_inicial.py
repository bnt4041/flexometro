"""core: organizaciones y activación de módulos

Revision ID: core_0001
Revises:
Create Date: 2026-08-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "core_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("core",)
depends_on: str | Sequence[str] | None = None

# Organización semilla del despliegue single-tenant inicial.
DEMO_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS core")

    op.create_table(
        "organization",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cif", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organization"),
        schema="core",
    )
    op.create_index(
        "ix_core_organization_slug", "organization", ["slug"], unique=True, schema="core"
    )

    op.create_table(
        "organization_module",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_code", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "activated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name="fk_organization_module_organization_id_organization",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_module"),
        sa.UniqueConstraint(
            "organization_id", "module_code", name="organization_module_unique"
        ),
        schema="core",
    )
    op.create_index(
        "ix_core_organization_module_organization_id",
        "organization_module",
        ["organization_id"],
        schema="core",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO core.organization (id, slug, name, is_active, settings)
            VALUES (CAST(:id AS uuid), 'demo', 'Organización de desarrollo', true, '{}'::jsonb)
            """
        ).bindparams(id=DEMO_ORG_ID)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO core.organization_module
                (id, organization_id, module_code, is_active)
            VALUES (gen_random_uuid(), CAST(:org_id AS uuid), 'presupuestos', true)
            """
        ).bindparams(org_id=DEMO_ORG_ID)
    )


def downgrade() -> None:
    op.drop_table("organization_module", schema="core")
    op.drop_table("organization", schema="core")
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")
