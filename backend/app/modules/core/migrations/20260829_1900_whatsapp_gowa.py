"""core: configuración de WhatsApp saliente

Tabla de una sola fila (`id=1`), como el resto de ajustes de plataforma: un
único número de WhatsApp para todo Flexómetro.

Las credenciales de los DOS proveedores viven en la misma fila y `proveedor`
dice cuál manda. Hoy es el puente de WhatsApp Web (GOWA), que vale para
enseñar el producto; el día que esto funcione como empresa habrá que pasar a
la API oficial de Meta, y tener aquí sus columnas permite dejarla configurada
y probada ANTES de apagar el puente.

`activa` arranca en falso a propósito. La fila se crea sola la primera vez
que alguien abre los ajustes, y si naciera activada el circuito de firma
empezaría a intentar hablar con un proveedor que todavía no existe.

Revision ID: core_whatsapp_0001
Revises: core_ia_vision_0001
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "core_whatsapp_0001"
down_revision: str | None = "core_ia_vision_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "configuracion_whatsapp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "proveedor",
            sa.Enum("gowa", "cloud", name="proveedor_whatsapp", native_enum=False, length=32),
            nullable=False,
            server_default=sa.text("'gowa'"),
        ),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "prefijo_pais", sa.String(length=5), nullable=False, server_default=sa.text("'34'")
        ),
        # Puente WhatsApp Web (GOWA)
        sa.Column("base_url", sa.String(length=200), nullable=True),
        sa.Column("usuario", sa.String(length=100), nullable=True),
        sa.Column("password", sa.String(length=200), nullable=True),
        sa.Column("device_id", sa.String(length=100), nullable=True),
        # API oficial (Cloud API de Meta)
        sa.Column("cloud_phone_number_id", sa.String(length=60), nullable=True),
        sa.Column("cloud_token", sa.String(length=400), nullable=True),
        sa.Column(
            "cloud_version", sa.String(length=10), nullable=False, server_default=sa.text("'v21.0'")
        ),
        sa.Column("plantilla_aviso", sa.String(length=100), nullable=True),
        sa.Column("plantilla_codigo", sa.String(length=100), nullable=True),
        sa.Column(
            "idioma_plantilla", sa.String(length=10), nullable=False, server_default=sa.text("'es'")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_configuracion_whatsapp")),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("configuracion_whatsapp", schema="core")
