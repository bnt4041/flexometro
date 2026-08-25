"""compras: la solicitud pasa a ser un paquete que se manda a varios proveedores

Hasta ahora una `solicitud_precios` ERA la petición a un proveedor: llevaba su
`proveedor_id`, su enlace, su estado y su oferta. Comparar tres proveedores
obligaba a crear tres solicitudes paralelas que solo coincidían por casualidad.

Se desdobla en cuatro responsabilidades:

- `solicitud_precios`  → QUÉ se pide, con nombre propio ("Yeserías").
- `solicitud_linea`    → cada línea de eso, una sola vez y común a todos.
- `solicitud_destinatario` (nueva) → A QUIÉN se le pide. Uno por proveedor,
  con su enlace, su estado y su presupuesto-oferta.
- `oferta_linea` (nueva) → POR CUÁNTO. Una fila por (destinatario, línea), y
  solo cuando el proveedor escribe algo: la ausencia de fila es "no lo ha
  cotizado", que es el hueco que se enseña en el comparativo.

Los datos existentes se conservan: cada solicitud actual se convierte en un
paquete con exactamente un destinatario, y sus precios se mueven a
`oferta_linea`. Las columnas viejas no se borran hasta haber copiado todo.

Revision ID: compras_0005
Revises: compras_0004
Create Date: 2026-08-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "compras_0005"
down_revision: str | None = "compras_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS_NUEVAS_CON_RLS = ("solicitud_destinatario", "oferta_linea")


def upgrade() -> None:
    # --- 1. Título del paquete -------------------------------------------
    op.add_column(
        "solicitud_precios",
        sa.Column("titulo", sa.String(length=200), nullable=True),
        schema="compras",
    )
    # Las que ya existen no tienen nombre: se les pone su propio código, que
    # es como el usuario las ha estado identificando hasta ahora.
    op.execute("UPDATE compras.solicitud_precios SET titulo = codigo WHERE titulo IS NULL")
    op.alter_column("solicitud_precios", "titulo", nullable=False, schema="compras")

    # --- 2. Destinatarios -------------------------------------------------
    op.create_table(
        "solicitud_destinatario",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("solicitud_id", sa.UUID(), nullable=False),
        sa.Column("proveedor_id", sa.UUID(), nullable=False),
        sa.Column("email_destino", sa.String(length=200), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "borrador", "enviada", "respondida", "descartada",
                name="estado_destinatario", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respondida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oferta_presupuesto_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_solicitud_destinatario_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitud_id"], ["compras.solicitud_precios.id"],
            name=op.f("fk_solicitud_destinatario_solicitud_id_solicitud_precios"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proveedor_id"], ["terceros.tercero.id"],
            name=op.f("fk_solicitud_destinatario_proveedor_id_tercero"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_presupuesto_id"], ["presupuestos.presupuesto.id"],
            name=op.f("fk_solicitud_destinatario_oferta_presupuesto_id_presupuesto"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitud_destinatario")),
        sa.UniqueConstraint("solicitud_id", "proveedor_id", name="solicitud_destinatario_unico"),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_solicitud_destinatario_organization_id"), "solicitud_destinatario",
        ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_solicitud_destinatario_solicitud", "solicitud_destinatario",
        ["solicitud_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_solicitud_destinatario_proveedor", "solicitud_destinatario",
        ["proveedor_id"], schema="compras",
    )

    # Cada solicitud existente se convierte en un paquete de un destinatario.
    # `aprobada`/`caducada` no existen en el enum del destinatario: se mapean
    # a `respondida` y `descartada`, que es lo que significan desde su lado.
    op.execute(
        """
        INSERT INTO compras.solicitud_destinatario
            (id, organization_id, solicitud_id, proveedor_id, email_destino,
             estado, enviada_en, respondida_en, oferta_presupuesto_id)
        SELECT gen_random_uuid(), s.organization_id, s.id, s.proveedor_id, s.email_destino,
               CASE s.estado
                   WHEN 'aprobada' THEN 'respondida'
                   WHEN 'caducada' THEN 'descartada'
                   ELSE s.estado
               END,
               s.enviada_en, s.respondida_en, s.oferta_presupuesto_id
        FROM compras.solicitud_precios s
        """
    )

    # --- 3. Ofertas por línea --------------------------------------------
    op.create_table(
        "oferta_linea",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("destinatario_id", sa.UUID(), nullable=False),
        sa.Column("linea_id", sa.UUID(), nullable=False),
        sa.Column("precio_ofertado", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("observaciones_proveedor", sa.Text(), nullable=True),
        sa.Column("aprobada", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_oferta_linea_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["destinatario_id"], ["compras.solicitud_destinatario.id"],
            name=op.f("fk_oferta_linea_destinatario_id_solicitud_destinatario"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linea_id"], ["compras.solicitud_linea.id"],
            name=op.f("fk_oferta_linea_linea_id_solicitud_linea"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oferta_linea")),
        sa.UniqueConstraint("destinatario_id", "linea_id", name="oferta_linea_unica"),
        schema="compras",
    )
    op.create_index(
        op.f("ix_compras_oferta_linea_organization_id"), "oferta_linea",
        ["organization_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_oferta_linea_destinatario", "oferta_linea", ["destinatario_id"], schema="compras",
    )
    op.create_index(
        "ix_compras_oferta_linea_linea", "oferta_linea", ["linea_id"], schema="compras",
    )

    # Lo que ya hubiera ofertado el proveedor se mueve a su fila propia. Solo
    # las líneas con algo escrito: la ausencia de fila es "no cotizado".
    op.execute(
        """
        INSERT INTO compras.oferta_linea
            (id, organization_id, destinatario_id, linea_id,
             precio_ofertado, observaciones_proveedor, aprobada)
        SELECT gen_random_uuid(), l.organization_id, d.id, l.id,
               l.precio_ofertado, l.observaciones_proveedor, l.aprobada
        FROM compras.solicitud_linea l
        JOIN compras.solicitud_destinatario d ON d.solicitud_id = l.solicitud_id
        WHERE l.precio_ofertado IS NOT NULL
           OR l.observaciones_proveedor IS NOT NULL
           OR l.aprobada
        """
    )

    # --- 4. Adjudicación en la línea --------------------------------------
    op.add_column(
        "solicitud_linea",
        sa.Column("adjudicada_a_id", sa.UUID(), nullable=True),
        schema="compras",
    )
    op.create_foreign_key(
        op.f("fk_solicitud_linea_adjudicada_a_id_solicitud_destinatario"),
        "solicitud_linea", "solicitud_destinatario",
        ["adjudicada_a_id"], ["id"],
        source_schema="compras", referent_schema="compras", ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE compras.solicitud_linea l
        SET adjudicada_a_id = d.id
        FROM compras.solicitud_destinatario d
        WHERE d.solicitud_id = l.solicitud_id AND l.aprobada
        """
    )

    # --- 5. Los accesos cuelgan del destinatario --------------------------
    for tabla, unica in (("acceso_token", None), ("acceso_estado", "acceso_estado_solicitud_unique")):
        op.add_column(tabla, sa.Column("destinatario_id", sa.UUID(), nullable=True), schema="compras")
        op.execute(
            f"""
            UPDATE compras.{tabla} a
            SET destinatario_id = d.id
            FROM compras.solicitud_destinatario d
            WHERE d.solicitud_id = a.solicitud_id
            """
        )
        # Un acceso sin destinatario no puede existir: si quedara alguno
        # huérfano, mejor que reviente aquí que dejar un enlace que no
        # resuelve a nadie.
        op.execute(f"DELETE FROM compras.{tabla} WHERE destinatario_id IS NULL")
        op.alter_column(tabla, "destinatario_id", nullable=False, schema="compras")
        if unica:
            op.drop_constraint(unica, tabla, schema="compras", type_="unique")
        op.drop_constraint(
            f"fk_{tabla}_solicitud_id_solicitud_precios", tabla, schema="compras", type_="foreignkey"
        )
        op.drop_column(tabla, "solicitud_id", schema="compras")
        op.create_foreign_key(
            op.f(f"fk_{tabla}_destinatario_id_solicitud_destinatario"),
            tabla, "solicitud_destinatario",
            ["destinatario_id"], ["id"],
            source_schema="compras", referent_schema="compras", ondelete="CASCADE",
        )
    op.create_unique_constraint(
        "acceso_estado_destinatario_unique", "acceso_estado", ["destinatario_id"], schema="compras"
    )

    # --- 6. Ya está todo copiado: fuera lo viejo --------------------------
    op.drop_column("solicitud_linea", "precio_ofertado", schema="compras")
    op.drop_column("solicitud_linea", "observaciones_proveedor", schema="compras")
    op.drop_column("solicitud_linea", "aprobada", schema="compras")

    op.drop_index("ix_compras_solicitud_precios_proveedor", table_name="solicitud_precios", schema="compras")
    op.drop_constraint(
        "fk_solicitud_precios_proveedor_id_tercero", "solicitud_precios",
        schema="compras", type_="foreignkey",
    )
    op.drop_constraint(
        "fk_solicitud_precios_oferta_presupuesto_id_presupuesto", "solicitud_precios",
        schema="compras", type_="foreignkey",
    )
    op.drop_column("solicitud_precios", "proveedor_id", schema="compras")
    op.drop_column("solicitud_precios", "email_destino", schema="compras")
    op.drop_column("solicitud_precios", "oferta_presupuesto_id", schema="compras")
    op.drop_column("solicitud_precios", "enviada_en", schema="compras")
    op.drop_column("solicitud_precios", "respondida_en", schema="compras")

    for tabla in _TABLAS_NUEVAS_CON_RLS:
        activar_rls("compras", tabla)
    conceder_privilegios_app("compras")


def downgrade() -> None:
    # Vuelta atrás destructiva por naturaleza: un paquete con varios
    # destinatarios no cabe en el modelo viejo. Se conserva el primero de cada
    # solicitud y se pierden los demás, que es lo mejor que se puede hacer.
    for tabla in reversed(_TABLAS_NUEVAS_CON_RLS):
        desactivar_rls("compras", tabla)

    op.add_column("solicitud_precios", sa.Column("proveedor_id", sa.UUID(), nullable=True), schema="compras")
    op.add_column("solicitud_precios", sa.Column("email_destino", sa.String(length=200), nullable=True), schema="compras")
    op.add_column("solicitud_precios", sa.Column("oferta_presupuesto_id", sa.UUID(), nullable=True), schema="compras")
    op.add_column("solicitud_precios", sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True), schema="compras")
    op.add_column("solicitud_precios", sa.Column("respondida_en", sa.DateTime(timezone=True), nullable=True), schema="compras")
    op.execute(
        """
        UPDATE compras.solicitud_precios s
        SET proveedor_id = d.proveedor_id, email_destino = d.email_destino,
            oferta_presupuesto_id = d.oferta_presupuesto_id,
            enviada_en = d.enviada_en, respondida_en = d.respondida_en
        FROM (
            SELECT DISTINCT ON (solicitud_id) * FROM compras.solicitud_destinatario
            ORDER BY solicitud_id, created_at
        ) d
        WHERE d.solicitud_id = s.id
        """
    )
    op.execute("DELETE FROM compras.solicitud_precios WHERE proveedor_id IS NULL")
    op.alter_column("solicitud_precios", "proveedor_id", nullable=False, schema="compras")
    op.create_foreign_key(
        "fk_solicitud_precios_proveedor_id_tercero", "solicitud_precios", "tercero",
        ["proveedor_id"], ["id"], source_schema="compras", referent_schema="terceros", ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_solicitud_precios_oferta_presupuesto_id_presupuesto", "solicitud_precios", "presupuesto",
        ["oferta_presupuesto_id"], ["id"], source_schema="compras", referent_schema="presupuestos", ondelete="SET NULL",
    )
    op.create_index(
        "ix_compras_solicitud_precios_proveedor", "solicitud_precios", ["proveedor_id"], schema="compras"
    )

    op.add_column("solicitud_linea", sa.Column("precio_ofertado", sa.Numeric(14, 2), nullable=True), schema="compras")
    op.add_column("solicitud_linea", sa.Column("observaciones_proveedor", sa.Text(), nullable=True), schema="compras")
    op.add_column(
        "solicitud_linea",
        sa.Column("aprobada", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="compras",
    )
    op.execute(
        """
        UPDATE compras.solicitud_linea l
        SET precio_ofertado = o.precio_ofertado,
            observaciones_proveedor = o.observaciones_proveedor,
            aprobada = o.aprobada
        FROM compras.oferta_linea o
        JOIN compras.solicitud_destinatario d ON d.id = o.destinatario_id
        WHERE o.linea_id = l.id AND d.solicitud_id = l.solicitud_id
        """
    )

    for tabla in ("acceso_token", "acceso_estado"):
        op.add_column(tabla, sa.Column("solicitud_id", sa.UUID(), nullable=True), schema="compras")
        op.execute(
            f"""
            UPDATE compras.{tabla} a
            SET solicitud_id = d.solicitud_id
            FROM compras.solicitud_destinatario d
            WHERE d.id = a.destinatario_id
            """
        )
        op.execute(f"DELETE FROM compras.{tabla} WHERE solicitud_id IS NULL")
        op.alter_column(tabla, "solicitud_id", nullable=False, schema="compras")
        op.drop_constraint(
            op.f(f"fk_{tabla}_destinatario_id_solicitud_destinatario"), tabla,
            schema="compras", type_="foreignkey",
        )
        op.drop_column(tabla, "destinatario_id", schema="compras")
        op.create_foreign_key(
            f"fk_{tabla}_solicitud_id_solicitud_precios", tabla, "solicitud_precios",
            ["solicitud_id"], ["id"], source_schema="compras", referent_schema="compras", ondelete="CASCADE",
        )
    op.create_unique_constraint(
        "acceso_estado_solicitud_unique", "acceso_estado", ["solicitud_id"], schema="compras"
    )

    op.drop_constraint(
        op.f("fk_solicitud_linea_adjudicada_a_id_solicitud_destinatario"), "solicitud_linea",
        schema="compras", type_="foreignkey",
    )
    op.drop_column("solicitud_linea", "adjudicada_a_id", schema="compras")
    op.drop_table("oferta_linea", schema="compras")
    op.drop_table("solicitud_destinatario", schema="compras")
    op.drop_column("solicitud_precios", "titulo", schema="compras")
