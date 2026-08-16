"""terceros: clientes, proveedores, subcontratistas y contactos

Revision ID: terceros_0001
Revises:
Create Date: 2026-08-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "terceros_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("terceros",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS terceros")

    op.create_table(
        "tercero",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("nif", sa.String(length=20), nullable=True),
        sa.Column("razon_social", sa.String(length=200), nullable=False),
        sa.Column("nombre_comercial", sa.String(length=200), nullable=True),
        sa.Column(
            "tipo_persona",
            sa.Enum("fisica", "juridica", name="tipo_persona", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("es_cliente", sa.Boolean(), nullable=False),
        sa.Column("es_proveedor", sa.Boolean(), nullable=False),
        sa.Column("es_subcontratista", sa.Boolean(), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("web", sa.String(length=200), nullable=True),
        sa.Column("direccion", sa.String(length=250), nullable=True),
        sa.Column("codigo_postal", sa.String(length=10), nullable=True),
        sa.Column("ciudad", sa.String(length=120), nullable=True),
        sa.Column("provincia", sa.String(length=120), nullable=True),
        sa.Column("pais", sa.String(length=2), nullable=False),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column(
            "forma_pago",
            sa.Enum(
                "transferencia",
                "domiciliado",
                "pagare",
                "confirming",
                "efectivo",
                "tarjeta",
                name="forma_pago",
                native_enum=False,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("dias_pago", sa.Integer(), nullable=True),
        sa.Column("irpf_retencion", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("inversion_sujeto_pasivo", sa.Boolean(), nullable=False),
        sa.Column("rea_numero", sa.String(length=40), nullable=True),
        sa.Column("rea_caducidad", sa.Date(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "origen_dato",
            sa.Enum(
                "manual", "fiebdc3", "ia", "importado",
                name="origen_dato", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("datos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_tercero_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tercero")),
        sa.UniqueConstraint("organization_id", "codigo", name="tercero_codigo_unique"),
        sa.UniqueConstraint("organization_id", "nif", name="tercero_nif_unique"),
        schema="terceros",
    )
    op.create_index(
        op.f("ix_terceros_tercero_organization_id"),
        "tercero", ["organization_id"], unique=False, schema="terceros",
    )
    op.create_index(
        "ix_terceros_tercero_razon_social",
        "tercero", ["organization_id", "razon_social"], unique=False, schema="terceros",
    )

    op.create_table(
        "contacto",
        sa.Column("tercero_id", sa.UUID(), nullable=True),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("apellidos", sa.String(length=160), nullable=True),
        sa.Column("cargo", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("movil", sa.String(length=30), nullable=True),
        sa.Column("es_principal", sa.Boolean(), nullable=False),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_contacto_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tercero_id"],
            ["terceros.tercero.id"],
            name=op.f("fk_contacto_tercero_id_tercero"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacto")),
        schema="terceros",
    )
    op.create_index(
        "ix_terceros_contacto_nombre",
        "contacto", ["organization_id", "nombre"], unique=False, schema="terceros",
    )
    op.create_index(
        op.f("ix_terceros_contacto_organization_id"),
        "contacto", ["organization_id"], unique=False, schema="terceros",
    )
    op.create_index(
        op.f("ix_terceros_contacto_tercero_id"),
        "contacto", ["tercero_id"], unique=False, schema="terceros",
    )


def downgrade() -> None:
    op.drop_table("contacto", schema="terceros")
    op.drop_table("tercero", schema="terceros")
    op.execute("DROP SCHEMA IF EXISTS terceros CASCADE")
