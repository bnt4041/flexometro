"""obras: una obra puede ejecutar varios presupuestos

Hasta ahora `obra.presupuesto_id` era único: una obra, un presupuesto. En obra
real eso no se sostiene — se contratan adendas, imprevistos y ampliaciones
después de arrancar, y todo eso se ejecuta en la misma obra.

`obra.presupuesto_id` se conserva apuntando al PRINCIPAL (lo usan el informe de
costes, el PEM del listado y las certificaciones), pero se le quita la
unicidad: los demás cuelgan de `obra_presupuesto` como anexos.

La obra que ya existe se conserva tal cual y se le crea su fila `principal`.

Revision ID: obras_0003
Revises: obras_0002
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "obras_0003"
down_revision: str | None = "obras_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "obra_presupuesto",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("obra_id", sa.UUID(), nullable=False),
        sa.Column("presupuesto_id", sa.UUID(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "principal", "anexo", name="tipo_vinculo_obra", native_enum=False, length=32
            ),
            nullable=False,
        ),
        sa.Column("fecha_vinculacion", sa.Date(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_obra_presupuesto_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["obra_id"], ["obras.obra.id"],
            name=op.f("fk_obra_presupuesto_obra_id_obra"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_obra_presupuesto_presupuesto_id_presupuesto"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_obra_presupuesto")),
        sa.UniqueConstraint("obra_id", "presupuesto_id", name="obra_presupuesto_unico"),
        schema="obras",
    )
    op.create_index(
        op.f("ix_obras_obra_presupuesto_organization_id"), "obra_presupuesto",
        ["organization_id"], schema="obras",
    )
    op.create_index(
        "ix_obras_obra_presupuesto_obra", "obra_presupuesto", ["obra_id"], schema="obras",
    )

    # Cada obra existente se queda con su presupuesto como principal. Se hace
    # ANTES de tocar la restricción, para que no haya un instante en el que la
    # información de qué presupuesto es el principal no esté en ningún sitio.
    op.execute(
        """
        INSERT INTO obras.obra_presupuesto
            (id, organization_id, obra_id, presupuesto_id, tipo, fecha_vinculacion, orden)
        SELECT gen_random_uuid(), o.organization_id, o.id, o.presupuesto_id,
               'principal', COALESCE(o.fecha_inicio, o.created_at::date), 0
        FROM obras.obra o
        """
    )

    # Y ahora sí: la unicidad la lleva la tabla de vínculos.
    op.drop_constraint("obra_presupuesto_unique", "obra", schema="obras", type_="unique")

    activar_rls("obras", "obra_presupuesto")
    conceder_privilegios_app("obras")


def downgrade() -> None:
    desactivar_rls("obras", "obra_presupuesto")
    # Volver atrás solo cabe si ninguna obra tiene anexos: con dos
    # presupuestos en la misma obra, el modelo viejo no puede representarla.
    op.execute(
        """
        DO $$
        DECLARE sobrantes int;
        BEGIN
            SELECT count(*) INTO sobrantes FROM (
                SELECT obra_id FROM obras.obra_presupuesto
                GROUP BY obra_id HAVING count(*) > 1
            ) x;
            IF sobrantes > 0 THEN
                RAISE EXCEPTION 'Hay % obras con varios presupuestos: el modelo anterior no las admite', sobrantes;
            END IF;
        END $$;
        """
    )
    op.create_unique_constraint(
        "obra_presupuesto_unique", "obra", ["presupuesto_id"], schema="obras"
    )
    op.drop_table("obra_presupuesto", schema="obras")
