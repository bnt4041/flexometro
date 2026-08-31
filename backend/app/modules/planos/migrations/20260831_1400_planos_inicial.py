"""planos: biblioteca, hojas calibrables, capas y lo dibujado encima

Revision ID: pln_0001
Revises:
Create Date: 2026-08-31
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

revision: str = "pln_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("planos",)
depends_on: str | Sequence[str] | None = ("core", "presupuestos", "obras")

SCHEMA = "planos"
TABLAS = ("elemento_plano", "capa_plano", "hoja_plano", "plano")


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "plano",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("obra_id", sa.UUID(), nullable=True),
        sa.Column("presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("origen", sa.String(length=32), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plano")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_plano_organization_id_organization"), ondelete="CASCADE",
        ),
        # Desligar, no arrastrar: borrar una obra no debe llevarse por delante
        # los planos, que suelen sobrevivirla y valen para la siguiente.
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"], name=op.f("fk_plano_obra_id_obra"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_plano_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.UniqueConstraint("organization_id", "codigo", name="plano_codigo_unique"),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_planos_plano_organization_id"), "plano",
                    ["organization_id"], schema=SCHEMA)
    op.create_index("ix_planos_plano_obra", "plano", ["organization_id", "obra_id"],
                    schema=SCHEMA)

    op.create_table(
        "hoja_plano",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("plano_id", sa.UUID(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=True),
        sa.Column("ancho", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("alto", sa.Numeric(precision=12, scale=3), nullable=False),
        # Nueve decimales no es exceso: en un plano de situación una unidad
        # puede valer milésimas de metro, y redondear la escala redondea todas
        # las mediciones de la hoja.
        sa.Column("metros_por_unidad", sa.Numeric(precision=18, scale=9), nullable=True),
        sa.Column("calibracion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoja_plano")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_hoja_plano_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plano_id"], [f"{SCHEMA}.plano.id"], name=op.f("fk_hoja_plano_plano_id_plano"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("plano_id", "numero", name="hoja_plano_numero_unique"),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_planos_hoja_plano_organization_id"), "hoja_plano",
                    ["organization_id"], schema=SCHEMA)

    op.create_table(
        "capa_plano",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("plano_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("color", sa.String(length=9), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("bloqueada", sa.Boolean(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capa_plano")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_capa_plano_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plano_id"], [f"{SCHEMA}.plano.id"], name=op.f("fk_capa_plano_plano_id_plano"),
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_planos_capa_plano_organization_id"), "capa_plano",
                    ["organization_id"], schema=SCHEMA)

    op.create_table(
        "elemento_plano",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("hoja_id", sa.UUID(), nullable=False),
        sa.Column("capa_id", sa.UUID(), nullable=True),
        sa.Column("tipo", sa.String(length=32), nullable=False),
        sa.Column("geometria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=9), nullable=True),
        sa.Column("valor", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=True),
        sa.Column("linea_medicion_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_elemento_plano")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_elemento_plano_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hoja_id"], [f"{SCHEMA}.hoja_plano.id"],
            name=op.f("fk_elemento_plano_hoja_id_hoja_plano"), ondelete="CASCADE",
        ),
        # Quitar una capa no borra lo dibujado en ella: se queda sin capa.
        # Perder mediciones por ordenar las capas sería una trampa.
        sa.ForeignKeyConstraint(
            ["capa_id"], [f"{SCHEMA}.capa_plano.id"],
            name=op.f("fk_elemento_plano_capa_id_capa_plano"), ondelete="SET NULL",
        ),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_planos_elemento_plano_organization_id"), "elemento_plano",
                    ["organization_id"], schema=SCHEMA)
    op.create_index("ix_planos_elemento_hoja", "elemento_plano",
                    ["organization_id", "hoja_id"], schema=SCHEMA)

    conceder_privilegios_app(SCHEMA)
    for tabla in TABLAS:
        activar_rls(SCHEMA, tabla)


def downgrade() -> None:
    for tabla in TABLAS:
        desactivar_rls(SCHEMA, tabla)
    revocar_privilegios_app(SCHEMA)
    for tabla in TABLAS:
        op.drop_table(tabla, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
