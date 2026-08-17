"""documentos inicial

Revision ID: documentos_0001
Revises:
Create Date: 2026-08-16 17:00:00

Fase 30: `documento`, el índice de los ficheros subidos a MinIO sobre
cualquier objeto grande del negocio (tercero, presupuesto, obra,
certificación, factura). El contenido no vive aquí — solo `object_key`, ver
`app/core/storage.py` y el docstring de `documentos/models.py`.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls, revocar_privilegios_app

revision: str = "documentos_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("documentos",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS documentos")

    op.create_table(
        "documento",
        sa.Column(
            "entidad",
            sa.Enum(
                "tercero", "presupuesto", "obra", "certificacion", "factura",
                name="entidad_documento", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("entidad_id", sa.UUID(), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["core.organization.id"],
            name=op.f("fk_documento_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documento")),
        sa.UniqueConstraint("object_key", name="documento_object_key_unique"),
        schema="documentos",
    )
    op.create_index(
        op.f("ix_documentos_documento_organization_id"),
        "documento", ["organization_id"], unique=False, schema="documentos",
    )
    op.create_index(
        "ix_documentos_documento_entidad",
        "documento", ["organization_id", "entidad", "entidad_id"], unique=False, schema="documentos",
    )

    activar_rls("documentos", "documento")

    # Schema nuevo: sin esto el rol de mínimo privilegio no tiene ni USAGE
    # sobre él (lección de la Fase 7).
    conceder_privilegios_app("documentos")


def downgrade() -> None:
    revocar_privilegios_app("documentos")
    desactivar_rls("documentos", "documento")

    op.drop_index("ix_documentos_documento_entidad", table_name="documento", schema="documentos")
    op.drop_index(op.f("ix_documentos_documento_organization_id"), table_name="documento", schema="documentos")
    op.drop_table("documento", schema="documentos")
    op.execute("DROP SCHEMA IF EXISTS documentos CASCADE")
