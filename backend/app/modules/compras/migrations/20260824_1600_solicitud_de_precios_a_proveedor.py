"""compras: solicitud de precios a proveedor (separata) y su acceso por token

Cuatro tablas nuevas. Tres llevan RLS como cualquier tabla de negocio;
`acceso_token` NO, y es deliberado: el proveedor llega sin sesión, así que hay
que resolver a qué organización pertenece su enlace antes de que exista
contexto — y sin contexto una tabla con RLS devuelve cero filas. Es el mismo
problema que `core.organization`, que también está fuera de RLS por esto (ver
`core_0002`). Por eso `acceso_token` se queda en un hash y dos referencias, y
todo el estado mutable del enlace vive en `acceso_estado`, que sí tiene RLS.

Revision ID: compras_0003
Revises: compras_0002
Create Date: 2026-08-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "compras_0003"
down_revision: str | None = "compras_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ESTADOS = ("borrador", "enviada", "respondida", "aprobada", "descartada", "caducada")

# Con RLS. `acceso_token` queda fuera a propósito (ver el docstring del módulo).
_TABLAS_CON_RLS = ("solicitud_precios", "solicitud_linea", "acceso_estado")


def upgrade() -> None:
    op.create_table(
        "solicitud_precios",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("presupuesto_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(*_ESTADOS, name="estado_solicitud", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("fecha_limite", sa.Date(), nullable=True),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respondida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("oferta_presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("emisor_subject", sa.String(length=120), nullable=True),
        sa.Column("emisor_nombre", sa.String(length=200), nullable=True),
        sa.Column("creado_por_subject", sa.String(length=120), nullable=True),
        sa.Column("creado_por_nombre", sa.String(length=200), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_solicitud_precios_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_solicitud_precios_presupuesto_id_presupuesto"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["terceros.tercero.id"],
            name=op.f("fk_solicitud_precios_proveedor_id_tercero"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_solicitud_precios_oferta_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitud_precios")),
        sa.UniqueConstraint("organization_id", "codigo", name="solicitud_precios_codigo_unique"),
        schema="compras",
    )
    op.create_index(
        "ix_compras_solicitud_precios_presupuesto", "solicitud_precios", ["presupuesto_id"],
        schema="compras",
    )
    op.create_index(
        "ix_compras_solicitud_precios_proveedor", "solicitud_precios", ["proveedor_id"],
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_solicitud_precios_organization_id"), "solicitud_precios",
        ["organization_id"], schema="compras",
    )

    op.create_table(
        "solicitud_linea",
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column("partida_id", sa.UUID(), nullable=True),
        sa.Column("capitulo_resumen", sa.String(length=250), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=True),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=False),
        sa.Column("medicion", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("precio_ofertado", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("observaciones_proveedor", sa.Text(), nullable=True),
        sa.Column("aprobada", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_solicitud_linea_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["compras.solicitud_precios.id"],
            name=op.f("fk_solicitud_linea_solicitud_id_solicitud_precios"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["partida_id"], ["presupuestos.partida.id"],
            name=op.f("fk_solicitud_linea_partida_id_partida"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitud_linea")),
        schema="compras",
    )
    op.create_index(
        "ix_compras_solicitud_linea_solicitud", "solicitud_linea", ["solicitud_id"], schema="compras"
    )
    op.create_index(
        op.f("ix_compras_solicitud_linea_organization_id"), "solicitud_linea",
        ["organization_id"], schema="compras",
    )

    # --- SIN RLS, a propósito. Ver el docstring del módulo. ---
    op.create_table(
        "acceso_token",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_acceso_token_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["compras.solicitud_precios.id"],
            name=op.f("fk_acceso_token_solicitud_id_solicitud_precios"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acceso_token")),
        sa.UniqueConstraint("token_hash", name="acceso_token_hash_unique"),
        schema="compras",
    )

    op.create_table(
        "acceso_estado",
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("usos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("usos_ia", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ficheros_subidos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("ultimo_uso_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_acceso_estado_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["compras.solicitud_precios.id"],
            name=op.f("fk_acceso_estado_solicitud_id_solicitud_precios"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acceso_estado")),
        sa.UniqueConstraint("solicitud_id", name="acceso_estado_solicitud_unique"),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_acceso_estado_organization_id"), "acceso_estado",
        ["organization_id"], schema="compras",
    )

    for tabla in _TABLAS_CON_RLS:
        activar_rls("compras", tabla)

    conceder_privilegios_app("compras")


def downgrade() -> None:
    for tabla in reversed(_TABLAS_CON_RLS):
        desactivar_rls("compras", tabla)

    op.drop_table("acceso_estado", schema="compras")
    op.drop_table("acceso_token", schema="compras")
    op.drop_table("solicitud_linea", schema="compras")
    op.drop_table("solicitud_precios", schema="compras")
