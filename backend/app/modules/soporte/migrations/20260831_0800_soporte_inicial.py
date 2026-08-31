"""soporte: tickets, wiki y búsqueda por significado

La extensión `vector` se crea aquí y no a mano: una instalación nueva tiene
que quedar funcionando con `alembic upgrade heads` y nada más.

El índice del vector es IVFFlat con 100 listas. Con pocos miles de fragmentos
una búsqueda secuencial ya es instantánea, así que el índice es previsión: a
partir de unas decenas de miles empieza a notarse. `lists=100` es lo
razonable hasta el orden de cien mil filas.

Revision ID: sop_0001
Revises:
Create Date: 2026-08-31
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.rls import (
    activar_rls,
    conceder_privilegios_app,
    desactivar_rls,
    revocar_privilegios_app,
)

revision: str = "sop_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("soporte",)
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "soporte"
DIMENSIONES = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "ticket",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum("incidencia", "peticion", "duda", name="tipo_ticket",
                    native_enum=False, length=32),
            nullable=False, server_default="peticion",
        ),
        sa.Column(
            "estado",
            sa.Enum("nuevo", "abierto", "esperando", "resuelto", "cerrado",
                    name="estado_ticket", native_enum=False, length=32),
            nullable=False, server_default="nuevo",
        ),
        sa.Column(
            "prioridad",
            sa.Enum("baja", "normal", "alta", "urgente", name="prioridad_ticket",
                    native_enum=False, length=32),
            nullable=False, server_default="normal",
        ),
        sa.Column("asignado_a_subject", sa.String(length=120), nullable=True),
        sa.Column("asignado_a_nombre", sa.String(length=200), nullable=True),
        sa.Column("ruta_origen", sa.String(length=400), nullable=True),
        sa.Column("resuelto_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["core.organization.id"],
                                name=op.f("fk_ticket_organization_id_organization"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_soporte_ticket_organization_id"), "ticket", ["organization_id"], schema=SCHEMA)
    op.create_index("ix_soporte_ticket_estado", "ticket", ["organization_id", "estado"], schema=SCHEMA)

    op.create_table(
        "mensaje_ticket",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("interno", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("de_ia", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["core.organization.id"],
                                name=op.f("fk_mensaje_ticket_organization_id_organization"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], [f"{SCHEMA}.ticket.id"],
                                name=op.f("fk_mensaje_ticket_ticket_id_ticket"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mensaje_ticket")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_soporte_mensaje_ticket_organization_id"), "mensaje_ticket",
                    ["organization_id"], schema=SCHEMA)

    op.create_table(
        "pagina_wiki",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False, server_default=""),
        sa.Column("categoria", sa.String(length=80), nullable=True),
        sa.Column("publicada", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("indexada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["core.organization.id"],
                                name=op.f("fk_pagina_wiki_organization_id_organization"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pagina_wiki")),
        sa.UniqueConstraint("organization_id", "slug", name="pagina_wiki_slug_unique"),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_soporte_pagina_wiki_organization_id"), "pagina_wiki",
                    ["organization_id"], schema=SCHEMA)

    op.create_table(
        "fragmento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "origen",
            sa.Enum("wiki", "ticket", name="origen_fragmento", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("origen_id", sa.UUID(), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", sa.dialects.postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["core.organization.id"],
                                name=op.f("fk_fragmento_organization_id_organization"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fragmento")),
        schema=SCHEMA,
    )
    # La columna se declara como `vector` de verdad aquí: Alembic no conoce el
    # tipo de pgvector, así que se crea con ARRAY arriba y se convierte.
    op.execute(f"ALTER TABLE {SCHEMA}.fragmento ALTER COLUMN embedding TYPE vector({DIMENSIONES})")
    op.create_index(op.f("ix_soporte_fragmento_organization_id"), "fragmento",
                    ["organization_id"], schema=SCHEMA)
    op.create_index("ix_soporte_fragmento_origen", "fragmento",
                    ["organization_id", "origen", "origen_id"], schema=SCHEMA)
    op.execute(
        f"CREATE INDEX ix_soporte_fragmento_vector ON {SCHEMA}.fragmento "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    conceder_privilegios_app(SCHEMA)
    for tabla in ("ticket", "mensaje_ticket", "pagina_wiki", "fragmento"):
        activar_rls(SCHEMA, tabla)


def downgrade() -> None:
    for tabla in ("fragmento", "pagina_wiki", "mensaje_ticket", "ticket"):
        desactivar_rls(SCHEMA, tabla)
    revocar_privilegios_app(SCHEMA)
    op.drop_table("fragmento", schema=SCHEMA)
    op.drop_table("pagina_wiki", schema=SCHEMA)
    op.drop_table("mensaje_ticket", schema=SCHEMA)
    op.drop_table("ticket", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
    # La extensión NO se borra: puede haberla usado otra cosa.
