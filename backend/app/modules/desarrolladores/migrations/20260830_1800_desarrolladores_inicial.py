"""desarrolladores: claves de API y webhooks

La puerta para integrar Flexómetro con otros sistemas.

De la clave solo se guarda su SHA-256; el `prefijo` va en claro para poder
reconocerla en pantalla y para buscarla sin comparar contra todas las filas.
El secreto del webhook SÍ va en claro, y es al revés a propósito: hace falta
para firmar cada envío, y una firma no se calcula con un hash.

Revision ID: dev_0001
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

revision: str = "dev_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("desarrolladores",)
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "desarrolladores"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "clave_api",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("prefijo", sa.String(length=16), nullable=False),
        sa.Column("clave_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "ambitos", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_uso_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_clave_api_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clave_api")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_desarrolladores_clave_api_organization_id"),
        "clave_api", ["organization_id"], schema=SCHEMA,
    )
    # Único GLOBAL, no por organización: al llegar una petición todavía no se
    # sabe de quién es — el prefijo es justo lo que lo averigua.
    op.create_index(
        "ix_desarrolladores_clave_prefijo", "clave_api", ["prefijo"], unique=True, schema=SCHEMA
    )

    op.create_table(
        "suscripcion_webhook",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column(
            "eventos", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("secreto", sa.String(length=64), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_suscripcion_webhook_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suscripcion_webhook")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_desarrolladores_suscripcion_webhook_organization_id"),
        "suscripcion_webhook", ["organization_id"], schema=SCHEMA,
    )
    op.create_index(
        "ix_desarrolladores_webhook_org", "suscripcion_webhook",
        ["organization_id", "activa"], schema=SCHEMA,
    )

    op.create_table(
        "entrega_webhook",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("suscripcion_id", sa.UUID(), nullable=False),
        sa.Column("evento", sa.String(length=64), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "entregada", "fallida", "agotada",
                name="estado_entrega", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proximo_intento_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entregada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respuesta_codigo", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_entrega_webhook_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["suscripcion_id"], [f"{SCHEMA}.suscripcion_webhook.id"],
            name=op.f("fk_entrega_webhook_suscripcion_id_suscripcion_webhook"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entrega_webhook")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_desarrolladores_entrega_webhook_organization_id"),
        "entrega_webhook", ["organization_id"], schema=SCHEMA,
    )
    op.create_index(
        "ix_desarrolladores_entrega_pendiente", "entrega_webhook",
        ["estado", "proximo_intento_en"], schema=SCHEMA,
    )

    conceder_privilegios_app(SCHEMA)
    # `clave_api` NO lleva RLS: se busca ANTES de saber a qué organización
    # pertenece la petición, que es precisamente lo que averigua. Con RLS
    # puesta, la consulta de autenticación no vería nunca ninguna fila.
    # El aislamiento lo da el índice único del prefijo más el hash.
    for tabla in ("suscripcion_webhook", "entrega_webhook"):
        activar_rls(SCHEMA, tabla)


def downgrade() -> None:
    for tabla in ("entrega_webhook", "suscripcion_webhook"):
        desactivar_rls(SCHEMA, tabla)
    revocar_privilegios_app(SCHEMA)
    op.drop_table("entrega_webhook", schema=SCHEMA)
    op.drop_table("suscripcion_webhook", schema=SCHEMA)
    op.drop_table("clave_api", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
