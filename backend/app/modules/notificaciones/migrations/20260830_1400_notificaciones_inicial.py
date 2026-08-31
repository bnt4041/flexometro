"""notificaciones: suscripciones de aviso

La bandeja (la campana) ya existía en `core`, pero solo la llenaba un sitio
del código a mano. Esto es la capa que faltaba: quién quiere enterarse de qué
y por dónde, configurable sin tocar código.

La unidad es la SUSCRIPCIÓN —un destinatario, un tipo de evento, sus canales
y su plazo— y no una «regla» con lista de destinatarios: los canales son de
quien recibe, no del aviso. Dos grupos pueden querer lo mismo por vías
distintas, y con los canales fuera habría que duplicar la regla para eso.

Revision ID: notif_0001
Revises:
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import (
    activar_rls,
    conceder_privilegios_app,
    desactivar_rls,
    revocar_privilegios_app,
)

revision: str = "notif_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("notificaciones",)
#: `core` por los grupos a los que puede apuntar una suscripción.
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "notificaciones"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "suscripcion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("tipo_evento", sa.String(length=64), nullable=False),
        sa.Column("usuario_subject", sa.String(length=120), nullable=True),
        sa.Column("grupo_id", sa.UUID(), nullable=True),
        sa.Column(
            "canales", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "parametros", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_suscripcion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grupo_id"], ["core.grupo.id"],
            name=op.f("fk_suscripcion_grupo_id_grupo"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suscripcion")),
        sa.UniqueConstraint(
            "organization_id", "tipo_evento", "usuario_subject", "grupo_id",
            name="suscripcion_unique",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_notificaciones_suscripcion_organization_id"),
        "suscripcion", ["organization_id"], schema=SCHEMA,
    )
    op.create_index(
        "ix_notificaciones_suscripcion_evento", "suscripcion",
        ["organization_id", "tipo_evento", "activa"], schema=SCHEMA,
    )

    op.create_table(
        "aviso_emitido",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("suscripcion_id", sa.UUID(), nullable=False),
        sa.Column("clave", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_aviso_emitido_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suscripcion_id"], [f"{SCHEMA}.suscripcion.id"],
            name=op.f("fk_aviso_emitido_suscripcion_id_suscripcion"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aviso_emitido")),
        sa.UniqueConstraint("suscripcion_id", "clave", name="aviso_emitido_unique"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_notificaciones_aviso_emitido_organization_id"),
        "aviso_emitido", ["organization_id"], schema=SCHEMA,
    )

    op.create_table(
        "preferencia_usuario",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("usuario_subject", sa.String(length=120), nullable=False),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("silenciado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_preferencia_usuario_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preferencia_usuario")),
        sa.UniqueConstraint("organization_id", "usuario_subject", name="preferencia_unique"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_notificaciones_preferencia_usuario_organization_id"),
        "preferencia_usuario", ["organization_id"], schema=SCHEMA,
    )

    conceder_privilegios_app(SCHEMA)
    for tabla in ("suscripcion", "aviso_emitido", "preferencia_usuario"):
        activar_rls(SCHEMA, tabla)


def downgrade() -> None:
    for tabla in ("preferencia_usuario", "aviso_emitido", "suscripcion"):
        desactivar_rls(SCHEMA, tabla)
    revocar_privilegios_app(SCHEMA)
    op.drop_table("preferencia_usuario", schema=SCHEMA)
    op.drop_table("aviso_emitido", schema=SCHEMA)
    op.drop_table("suscripcion", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
