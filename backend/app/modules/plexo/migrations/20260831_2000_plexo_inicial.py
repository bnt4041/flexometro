"""plexo: vínculo entre organizaciones (universo Plexo)

La primera vez que una tabla no pertenece a una sola organización: `vinculo`
referencia a dos. `activar_rls()`/`activar_rls_maestro()` no sirven —el
primero exige un único `organization_id`, el segundo amplía SELECT a
«hermanas de la misma cuenta», que no es el caso aquí (cuentas distintas,
sin relación previa)— así que las políticas de esta migración son propias.

`perfil` sí pertenece a una sola organización, pero su SELECT tiene que
poder verse desde CUALQUIER organización cuando `visible = true` (para poder
buscarla) — variante de la misma idea que `activar_rls_maestro`, con un flag
en la fila en vez de «misma cuenta» como condición de ensanche.

Revision ID: plx_0001
Revises:
Create Date: 2026-08-31
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.rls import conceder_privilegios_app

revision: str = "plx_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("plexo",)
depends_on: str | Sequence[str] | None = ("core",)

SCHEMA = "plexo"
CONDICION_PROPIA = "organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # ── perfil ────────────────────────────────────────────────────────
    op.create_table(
        "perfil",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_perfil")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_perfil_organization_id_organization"), ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.execute(f"ALTER TABLE {SCHEMA}.perfil ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {SCHEMA}.perfil FORCE ROW LEVEL SECURITY")
    # SELECT ensanchado: tu propia fila, o cualquiera que se haya hecho
    # visible. INSERT/UPDATE/DELETE se quedan estrictos —nadie cambia la
    # visibilidad de otro— igual que exige el comentario de
    # `activar_rls_maestro` en `app/core/rls.py` sobre no combinar el
    # ensanche de SELECT con el de escritura.
    op.execute(
        f"CREATE POLICY perfil_select ON {SCHEMA}.perfil "
        f"FOR SELECT USING (({CONDICION_PROPIA}) OR visible = true)"
    )
    op.execute(
        f"CREATE POLICY perfil_insert ON {SCHEMA}.perfil "
        f"FOR INSERT WITH CHECK ({CONDICION_PROPIA})"
    )
    op.execute(
        f"CREATE POLICY perfil_update ON {SCHEMA}.perfil "
        f"FOR UPDATE USING ({CONDICION_PROPIA}) WITH CHECK ({CONDICION_PROPIA})"
    )
    op.execute(
        f"CREATE POLICY perfil_delete ON {SCHEMA}.perfil FOR DELETE USING ({CONDICION_PROPIA})"
    )

    # ── vinculo ───────────────────────────────────────────────────────
    op.create_table(
        "vinculo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizacion_origen_id", sa.UUID(), nullable=False),
        sa.Column("organizacion_destino_id", sa.UUID(), nullable=False),
        sa.Column("estado", sa.String(length=32), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=True),
        sa.Column("invitado_por_subject", sa.String(length=120), nullable=False),
        sa.Column("invitado_por_nombre", sa.String(length=200), nullable=False),
        sa.Column("respondido_por_subject", sa.String(length=120), nullable=True),
        sa.Column("respondido_por_nombre", sa.String(length=200), nullable=True),
        sa.Column("respondido_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vinculo")),
        sa.ForeignKeyConstraint(
            ["organizacion_origen_id"], ["core.organization.id"],
            name=op.f("fk_vinculo_organizacion_origen_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_destino_id"], ["core.organization.id"],
            name=op.f("fk_vinculo_organizacion_destino_id_organization"), ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "organizacion_origen_id <> organizacion_destino_id",
            name=op.f("ck_vinculo_origen_distinto_destino"),
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_plexo_vinculo_origen", "vinculo", ["organizacion_origen_id"],
                    schema=SCHEMA)
    op.create_index("ix_plexo_vinculo_destino", "vinculo", ["organizacion_destino_id"],
                    schema=SCHEMA)

    # Como mucho una invitación viva (pendiente o aceptada) por pareja de
    # organizaciones, sea quien sea quien invitó. `par_normalizado` usa
    # LEAST/GREATEST para que A→B y B→A caigan en el mismo valor; el índice
    # único es PARCIAL (solo pendiente/aceptado) para que un rechazo o una
    # revocación no bloqueen un intento posterior — esa fila vieja se queda
    # como historial, sin más.
    op.execute(
        f"""
        ALTER TABLE {SCHEMA}.vinculo ADD COLUMN par_normalizado text
        GENERATED ALWAYS AS (
            LEAST(organizacion_origen_id::text, organizacion_destino_id::text)
            || '|' ||
            GREATEST(organizacion_origen_id::text, organizacion_destino_id::text)
        ) STORED
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX ux_plexo_vinculo_pareja_activa ON {SCHEMA}.vinculo (par_normalizado)
        WHERE estado IN ('pendiente', 'aceptado')
        """
    )

    op.execute(f"ALTER TABLE {SCHEMA}.vinculo ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {SCHEMA}.vinculo FORCE ROW LEVEL SECURITY")
    condicion_participante = (
        "(organizacion_origen_id = NULLIF(current_setting('app.organization_id', true), '')::uuid "
        "OR organizacion_destino_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    op.execute(
        f"CREATE POLICY vinculo_select ON {SCHEMA}.vinculo FOR SELECT "
        f"USING ({condicion_participante})"
    )
    # INSERT: solo puedes crear una invitación DESDE tu propia organización —
    # si no, cualquiera podría fabricar un vínculo con tu nombre como origen.
    op.execute(
        f"CREATE POLICY vinculo_insert ON {SCHEMA}.vinculo FOR INSERT "
        f"WITH CHECK (organizacion_origen_id = "
        f"NULLIF(current_setting('app.organization_id', true), '')::uuid)"
    )
    # UPDATE: cualquiera de los dos lados puede tocar la fila —aceptar,
    # rechazar o revocar son cosas que hace el destino o el origen según el
    # caso—; QUÉ transición es legal para cuál lo decide `service.py`, no la
    # política. No hay DELETE: un vínculo se cierra con estado, no se borra.
    op.execute(
        f"CREATE POLICY vinculo_update ON {SCHEMA}.vinculo FOR UPDATE "
        f"USING ({condicion_participante}) WITH CHECK ({condicion_participante})"
    )

    conceder_privilegios_app(SCHEMA)


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS vinculo_update ON {SCHEMA}.vinculo")
    op.execute(f"DROP POLICY IF EXISTS vinculo_insert ON {SCHEMA}.vinculo")
    op.execute(f"DROP POLICY IF EXISTS vinculo_select ON {SCHEMA}.vinculo")
    op.drop_table("vinculo", schema=SCHEMA)

    for politica in ("perfil_delete", "perfil_update", "perfil_insert", "perfil_select"):
        op.execute(f"DROP POLICY IF EXISTS {politica} ON {SCHEMA}.perfil")
    op.drop_table("perfil", schema=SCHEMA)

    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
