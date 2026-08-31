"""automatizaciones: flujos de nodos

El flujo entero va en una columna JSONB y no en tablas de nodos y aristas: se
edita como una unidad, y el histórico necesita saber cómo era el flujo EN EL
MOMENTO de ejecutarse — con filas vivas eso se pierde al primer cambio.

Lo que sí son tablas es lo que pasó: ejecuciones y pasos, que se consultan
aparte y crecen sin parar.

Revision ID: auto_0001
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

revision: str = "auto_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("automatizaciones",)
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "automatizaciones"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "automatizacion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "definicion", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("evento_disparador", sa.String(length=64), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("proxima_ejecucion_en", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_automatizacion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_automatizacion")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_automatizaciones_automatizacion_organization_id"),
        "automatizacion", ["organization_id"], schema=SCHEMA,
    )
    op.create_index(
        "ix_automatizaciones_activa", "automatizacion",
        ["organization_id", "activa"], schema=SCHEMA,
    )
    # Único: dos flujos con el mismo token harían que una llamada no supiera
    # cuál arrancar. Y es por donde se busca en el disparo por webhook.
    op.create_index(
        "ix_automatizaciones_token", "automatizacion", ["token_hash"], unique=True, schema=SCHEMA
    )

    op.create_table(
        "ejecucion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("automatizacion_id", sa.UUID(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "en_curso", "completada", "fallida", "parcial",
                name="estado_ejecucion", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="en_curso",
        ),
        sa.Column("disparador", sa.String(length=64), nullable=False),
        sa.Column(
            "entrada", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("terminada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_ejecucion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["automatizacion_id"], [f"{SCHEMA}.automatizacion.id"],
            name=op.f("fk_ejecucion_automatizacion_id_automatizacion"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ejecucion")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_automatizaciones_ejecucion_organization_id"),
        "ejecucion", ["organization_id"], schema=SCHEMA,
    )
    op.create_index(
        "ix_automatizaciones_ejecucion_flujo", "ejecucion",
        ["automatizacion_id", "created_at"], schema=SCHEMA,
    )

    op.create_table(
        "paso_ejecucion",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("ejecucion_id", sa.UUID(), nullable=False),
        sa.Column("nodo_id", sa.String(length=64), nullable=False),
        sa.Column("tipo_nodo", sa.String(length=64), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "estado",
            sa.Enum("ok", "error", "omitido", name="estado_paso", native_enum=False, length=32),
            nullable=False,
            server_default="ok",
        ),
        sa.Column(
            "salida", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("ruta", sa.String(length=32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duracion_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_paso_ejecucion_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ejecucion_id"], [f"{SCHEMA}.ejecucion.id"],
            name=op.f("fk_paso_ejecucion_ejecucion_id_ejecucion"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paso_ejecucion")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_automatizaciones_paso_ejecucion_organization_id"),
        "paso_ejecucion", ["organization_id"], schema=SCHEMA,
    )

    conceder_privilegios_app(SCHEMA)
    # `automatizacion` NO lleva RLS: el disparo por webhook busca por token
    # ANTES de saber de qué organización es — igual que la clave de API. El
    # aislamiento lo da el índice único del hash del token.
    for tabla in ("ejecucion", "paso_ejecucion"):
        activar_rls(SCHEMA, tabla)


def downgrade() -> None:
    for tabla in ("paso_ejecucion", "ejecucion"):
        desactivar_rls(SCHEMA, tabla)
    revocar_privilegios_app(SCHEMA)
    op.drop_table("paso_ejecucion", schema=SCHEMA)
    op.drop_table("ejecucion", schema=SCHEMA)
    op.drop_table("automatizacion", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
