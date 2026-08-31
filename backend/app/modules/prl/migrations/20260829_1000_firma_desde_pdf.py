"""prl: mandar a firmar un PDF, no solo una plantilla

Hasta ahora una solicitud de firma solo podía nacer de una plantilla o de un
HTML escrito a mano. En la práctica lo que más se manda a firmar ya existe
como PDF: un plan de seguridad, un contrato, un anexo que llegó por correo.

`origen` distingue los tres casos y `documento_origen_id` guarda el fichero
cuando es un PDF. Va con RESTRICT y no con SET NULL: si se borrara el
documento, la solicitud firmada se quedaría sin poder acreditar QUÉ se firmó,
que es justo lo que la evidencia tiene que demostrar.

Las filas que ya existen se quedan con origen 'html' o 'plantilla' según
tengan o no plantilla asociada — es exactamente lo que eran.

Revision ID: prl_0002
Revises: prl_0001
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "prl_0002"
down_revision: str | None = "prl_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "solicitud_firma",
        sa.Column(
            "origen",
            sa.Enum("plantilla", "html", "pdf", name="origen_firma", native_enum=False, length=32),
            nullable=False,
            server_default="html",
        ),
        schema="prl",
    )
    op.add_column(
        "solicitud_firma",
        sa.Column("documento_origen_id", sa.UUID(), nullable=True),
        schema="prl",
    )
    op.create_foreign_key(
        op.f("fk_solicitud_firma_documento_origen_id_documento"),
        "solicitud_firma",
        "documento",
        ["documento_origen_id"],
        ["id"],
        source_schema="prl",
        referent_schema="documentos",
        ondelete="RESTRICT",
    )
    # Lo ya existente nació de una plantilla o de HTML suelto; se marca según
    # tenga plantilla, que es lo que de verdad fue.
    op.execute(
        "UPDATE prl.solicitud_firma SET origen = 'plantilla' WHERE plantilla_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_solicitud_firma_documento_origen_id_documento"),
        "solicitud_firma",
        schema="prl",
        type_="foreignkey",
    )
    op.drop_column("solicitud_firma", "documento_origen_id", schema="prl")
    op.drop_column("solicitud_firma", "origen", schema="prl")
