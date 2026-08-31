"""prl: varias firmas por documento

Un acta de coordinación la firman el contratista, la subcontrata y a veces el
coordinador de seguridad. Con el firmante incrustado en `solicitud_firma` eso
era imposible: había un nombre, un correo, un token y una firma.

`firmante` saca cada firma a su propia fila, y con ella todo lo que es del
acto individual: su enlace, su código de verificación, su IP, sus sellos de
tiempo y el recuadro donde va su firma. `firma_token` pasa a colgar del
firmante — cada persona tiene su propio enlace, igual que ya hacía
`compras.acceso_token` con cada destinatario de una solicitud de precios.

Los datos existentes NO se pierden: cada solicitud ya enviada se convierte en
un documento con exactamente un firmante, que es lo que era.

Revision ID: prl_0004
Revises: prl_0003
Create Date: 2026-08-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import activar_rls, desactivar_rls

revision: str = "prl_0004"
down_revision: str | None = "prl_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "firmante",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("contacto_id", sa.UUID(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "vista", "firmada", "rechazada",
                name="estado_firmante", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vista_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firmada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firmante_nombre", sa.String(length=160), nullable=True),
        sa.Column("firmante_dni", sa.String(length=20), nullable=True),
        sa.Column("firma_imagen", sa.Text(), nullable=True),
        sa.Column("ip_firma", sa.String(length=45), nullable=True),
        sa.Column("user_agent_firma", sa.String(length=400), nullable=True),
        sa.Column("motivo_rechazo", sa.Text(), nullable=True),
        sa.Column("otp_hash", sa.String(length=64), nullable=True),
        sa.Column("otp_expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("otp_verificado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posiciones_firma", postgresql.JSONB(), nullable=True),
        sa.Column("ultimo_aviso_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_firmante_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["prl.solicitud_firma.id"],
            name=op.f("fk_firmante_solicitud_id_solicitud_firma"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contacto_id"], ["terceros.contacto.id"],
            name=op.f("fk_firmante_contacto_id_contacto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_firmante")),
        schema="prl",
    )
    op.create_index(
        op.f("ix_prl_firmante_organization_id"), "firmante", ["organization_id"], schema="prl"
    )
    op.create_index("ix_prl_firmante_solicitud", "firmante", ["solicitud_id"], schema="prl")
    activar_rls("prl", "firmante")

    # ── Migración de datos: cada solicitud pasa a tener un firmante ──────
    # `estado` se traduce del documento a la persona, que hasta ahora eran lo
    # mismo. 'parcial' no puede aparecer: es un estado que solo existe desde
    # esta migración en adelante.
    op.execute(
        """
        INSERT INTO prl.firmante (
            id, organization_id, solicitud_id, orden, nombre, email, estado,
            enviada_en, vista_en, firmada_en, firmante_nombre, firmante_dni,
            firma_imagen, ip_firma, user_agent_firma, motivo_rechazo,
            otp_hash, otp_expira_en, otp_intentos, otp_verificado_en,
            posiciones_firma, created_at, updated_at
        )
        SELECT
            gen_random_uuid(), s.organization_id, s.id, 0,
            s.destinatario_nombre, s.destinatario_email,
            CASE s.estado
                WHEN 'firmada'   THEN 'firmada'
                WHEN 'rechazada' THEN 'rechazada'
                WHEN 'vista'     THEN 'vista'
                ELSE 'pendiente'
            END,
            s.enviada_en, s.vista_en, s.firmada_en, s.firmante_nombre, s.firmante_dni,
            s.firma_imagen, s.ip_firma, s.user_agent_firma, s.motivo_rechazo,
            s.otp_hash, s.otp_expira_en, s.otp_intentos, s.otp_verificado_en,
            s.posiciones_firma, s.created_at, s.updated_at
        FROM prl.solicitud_firma s
        """
    )

    # `firma_token` pasa a colgar del firmante. Se añade la columna, se
    # rellena desde la solicitud y solo entonces se hace obligatoria: hacerlo
    # NOT NULL de entrada fallaría con filas ya existentes.
    op.add_column("firma_token", sa.Column("firmante_id", sa.UUID(), nullable=True), schema="prl")
    op.execute(
        """
        UPDATE prl.firma_token t
        SET firmante_id = f.id
        FROM prl.firmante f
        WHERE f.solicitud_id = t.solicitud_id
        """
    )
    # Un token sin firmante no puede resolverse: se borra en vez de dejarlo
    # apuntando a la nada.
    op.execute("DELETE FROM prl.firma_token WHERE firmante_id IS NULL")
    op.alter_column("firma_token", "firmante_id", nullable=False, schema="prl")
    op.create_foreign_key(
        op.f("fk_firma_token_firmante_id_firmante"),
        "firma_token", "firmante", ["firmante_id"], ["id"],
        source_schema="prl", referent_schema="prl", ondelete="CASCADE",
    )
    op.drop_constraint(
        op.f("fk_firma_token_solicitud_id_solicitud_firma"),
        "firma_token", schema="prl", type_="foreignkey",
    )
    op.drop_column("firma_token", "solicitud_id", schema="prl")

    # ── La solicitud se queda solo con lo que es del DOCUMENTO ──────────
    for columna in (
        "destinatario_nombre", "destinatario_email", "vista_en", "firmada_en",
        "firmante_nombre", "firmante_dni", "firma_imagen", "ip_firma",
        "user_agent_firma", "motivo_rechazo", "otp_hash", "otp_expira_en",
        "otp_intentos", "otp_verificado_en", "posiciones_firma",
    ):
        op.drop_column("solicitud_firma", columna, schema="prl")


def downgrade() -> None:
    # Vuelta atrás con el PRIMER firmante de cada documento: con varios, los
    # demás se pierden — es inevitable, el modelo antiguo no los admite.
    for columna, tipo in [
        ("destinatario_nombre", sa.String(length=160)),
        ("destinatario_email", sa.String(length=200)),
        ("vista_en", sa.DateTime(timezone=True)),
        ("firmada_en", sa.DateTime(timezone=True)),
        ("firmante_nombre", sa.String(length=160)),
        ("firmante_dni", sa.String(length=20)),
        ("firma_imagen", sa.Text()),
        ("ip_firma", sa.String(length=45)),
        ("user_agent_firma", sa.String(length=400)),
        ("motivo_rechazo", sa.Text()),
        ("otp_hash", sa.String(length=64)),
        ("otp_expira_en", sa.DateTime(timezone=True)),
        ("otp_verificado_en", sa.DateTime(timezone=True)),
    ]:
        op.add_column("solicitud_firma", sa.Column(columna, tipo, nullable=True), schema="prl")
    op.add_column(
        "solicitud_firma",
        sa.Column("otp_intentos", sa.Integer(), nullable=False, server_default="0"),
        schema="prl",
    )
    op.add_column(
        "solicitud_firma", sa.Column("posiciones_firma", postgresql.JSONB(), nullable=True),
        schema="prl",
    )
    op.execute(
        """
        UPDATE prl.solicitud_firma s SET
            destinatario_nombre = f.nombre, destinatario_email = f.email,
            vista_en = f.vista_en, firmada_en = f.firmada_en,
            firmante_nombre = f.firmante_nombre, firmante_dni = f.firmante_dni,
            firma_imagen = f.firma_imagen, ip_firma = f.ip_firma,
            user_agent_firma = f.user_agent_firma, motivo_rechazo = f.motivo_rechazo,
            otp_hash = f.otp_hash, otp_expira_en = f.otp_expira_en,
            otp_intentos = f.otp_intentos, otp_verificado_en = f.otp_verificado_en,
            posiciones_firma = f.posiciones_firma
        FROM (SELECT DISTINCT ON (solicitud_id) * FROM prl.firmante ORDER BY solicitud_id, orden) f
        WHERE f.solicitud_id = s.id
        """
    )
    op.alter_column("solicitud_firma", "destinatario_nombre", nullable=False, schema="prl")
    op.alter_column("solicitud_firma", "destinatario_email", nullable=False, schema="prl")

    op.add_column("firma_token", sa.Column("solicitud_id", sa.UUID(), nullable=True), schema="prl")
    op.execute(
        "UPDATE prl.firma_token t SET solicitud_id = f.solicitud_id "
        "FROM prl.firmante f WHERE f.id = t.firmante_id"
    )
    op.execute("DELETE FROM prl.firma_token WHERE solicitud_id IS NULL")
    op.alter_column("firma_token", "solicitud_id", nullable=False, schema="prl")
    op.create_foreign_key(
        op.f("fk_firma_token_solicitud_id_solicitud_firma"),
        "firma_token", "solicitud_firma", ["solicitud_id"], ["id"],
        source_schema="prl", referent_schema="prl", ondelete="CASCADE",
    )
    op.drop_constraint(
        op.f("fk_firma_token_firmante_id_firmante"), "firma_token", schema="prl", type_="foreignkey"
    )
    op.drop_column("firma_token", "firmante_id", schema="prl")

    desactivar_rls("prl", "firmante")
    op.drop_table("firmante", schema="prl")
