"""fusión de producto en concepto: banco de precios (Fase 25)

Revision ID: presupuestos_0005
Revises: presupuestos_0004
Create Date: 2026-08-16 16:00:00

Se dispone tras `catalogo_0002`: hay que fusionar sus datos antes de poder
tocar la tabla que se va a borrar.

Fusiona `catalogo.Producto` en `presupuestos.Concepto` (un producto/servicio
y una partida unitaria son la misma ficha, el "banco de precios"), y con él
`Familia` y `PrecioSuministro` se mudan de schema. El módulo `catalogo` deja
de existir tras esta migración.

Reglas de la fusión, por organización:
- Un producto ya referenciado por exactamente un concepto (origen_precio
  PRODUCTO) le transfiere sus campos propios (ean, familia, precio de venta,
  tipo de IVA) a ESE concepto — es el caso normal, el único que existe hoy en
  producción (comprobado contra la base de datos real antes de escribir esta
  migración).
- Un producto sin ningún concepto que lo referencie se convierte en un
  concepto básico nuevo, con origen_precio PRODUCTO y el mismo código (los
  productos usan el prefijo "P", que nunca choca con B/A/U de concepto).
- Un producto referenciado por MÁS DE UN concepto es una ambigüedad real (¿a
  cuál de los dos le pertenece el EAN, la familia?) que esta migración se
  niega a resolver adivinando: aborta con un error explícito. No ha ocurrido
  nunca en los datos reales hasta ahora.

Cada `PrecioSuministro` y cada `AlbaranLinea` que apuntaba al producto pasa a
apuntar al concepto resultante.
"""
import uuid
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import activar_rls, conceder_privilegios_app, desactivar_rls

revision: str = "presupuestos_0005"
down_revision: str | None = "presupuestos_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = ("catalogo_0002", "compras", "63821d58ff8a")

_DOS_DECIMALES = Decimal("0.01")
_CUATRO_DECIMALES = Decimal("0.0001")


def _redondear(valor: Decimal, precision: Decimal) -> Decimal:
    return valor.quantize(precision, rounding=ROUND_HALF_UP)


def upgrade() -> None:
    conn = op.get_bind()

    # --- 1. Mudar Familia y PrecioSuministro al schema presupuestos ---
    # `ALTER TABLE ... SET SCHEMA` conserva datos, PK, FKs (incluida la
    # autorreferencia de familia) e índices tal cual — solo cambia dónde vive
    # la tabla. Los nombres de índice que llevaban "catalogo" incrustado se
    # renombran aparte, más abajo, por higiene (no tiene efecto funcional).
    op.execute("ALTER TABLE catalogo.familia SET SCHEMA presupuestos")
    op.execute("ALTER TABLE catalogo.precio_suministro SET SCHEMA presupuestos")

    op.execute(
        "ALTER INDEX presupuestos.ix_catalogo_familia_organization_id "
        "RENAME TO ix_presupuestos_familia_organization_id"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_catalogo_familia_parent_id "
        "RENAME TO ix_presupuestos_familia_parent_id"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_catalogo_precio_suministro_organization_id "
        "RENAME TO ix_presupuestos_precio_suministro_organization_id"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_catalogo_precio_suministro_producto "
        "RENAME TO ix_presupuestos_precio_suministro_concepto"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_catalogo_precio_suministro_proveedor "
        "RENAME TO ix_presupuestos_precio_suministro_proveedor"
    )
    op.execute(
        "ALTER INDEX presupuestos.uq_catalogo_precio_suministro_preferente "
        "RENAME TO uq_presupuestos_precio_suministro_preferente"
    )

    # --- 2. Nuevos campos de Concepto (todavía con producto_id: hace falta
    #     para encontrar qué concepto corresponde a qué producto) ---
    op.add_column("concepto", sa.Column("ean", sa.String(length=14), nullable=True), schema="presupuestos")
    op.add_column("concepto", sa.Column("familia_id", sa.UUID(), nullable=True), schema="presupuestos")
    op.add_column(
        "concepto",
        sa.Column("precio_venta", sa.Numeric(precision=14, scale=2), nullable=True),
        schema="presupuestos",
    )
    op.add_column(
        "concepto",
        sa.Column(
            "tipo_iva",
            sa.Enum(
                "general", "reducido", "superreducido", "exento",
                name="tipo_iva", native_enum=False, length=32,
            ),
            nullable=False,
            server_default="general",
        ),
        schema="presupuestos",
    )
    op.create_index(
        op.f("ix_presupuestos_concepto_familia_id"),
        "concepto", ["familia_id"], unique=False, schema="presupuestos",
    )
    op.create_foreign_key(
        op.f("fk_concepto_familia_id_familia"),
        "concepto", "familia", ["familia_id"], ["id"],
        source_schema="presupuestos", referent_schema="presupuestos",
        ondelete="SET NULL",
    )

    # --- 3. Quitar ya las FK que apuntan a catalogo.producto: los UPDATE de
    #     repunte (paso 5) escriben ids de concepto en estas columnas, y esa
    #     FK todavía-sin-renombrar no lo permitiría. ---
    op.drop_constraint(
        op.f("fk_precio_suministro_producto_id_producto"),
        "precio_suministro", schema="presupuestos", type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_albaran_linea_producto_id_producto"),
        "albaran_linea", schema="compras", type_="foreignkey",
    )

    # --- 4. La fusión propiamente dicha, producto a producto ---
    productos = conn.execute(
        sa.text(
            "SELECT id, organization_id, codigo, tipo, familia_id, resumen, unidad, "
            "tipo_iva, precio_venta, ean, activo, origen_dato, atributos::text AS atributos "
            "FROM catalogo.producto"
        )
    ).fetchall()

    # producto.id -> concepto.id resultante, para repuntar precio_suministro
    # y albaran_linea en el siguiente paso.
    concepto_de_producto: dict[uuid.UUID, uuid.UUID] = {}

    for producto in productos:
        conceptos_vinculados = conn.execute(
            sa.text(
                "SELECT id FROM presupuestos.concepto "
                "WHERE producto_id = :producto_id AND organization_id = :org_id"
            ),
            {"producto_id": producto.id, "org_id": producto.organization_id},
        ).fetchall()

        if len(conceptos_vinculados) > 1:
            raise RuntimeError(
                f"El producto '{producto.codigo}' ({producto.id}) tiene más de un "
                "concepto vinculado; esta migración no puede decidir a cuál "
                "de ellos pertenecen el EAN, la familia y el precio de venta. "
                "Resuélvelo a mano antes de continuar."
            )

        if conceptos_vinculados:
            concepto_id = conceptos_vinculados[0].id
            conn.execute(
                sa.text(
                    "UPDATE presupuestos.concepto SET "
                    "ean = :ean, familia_id = :familia_id, "
                    "precio_venta = :precio_venta, tipo_iva = :tipo_iva "
                    "WHERE id = :concepto_id"
                ),
                {
                    "ean": producto.ean,
                    "familia_id": producto.familia_id,
                    "precio_venta": producto.precio_venta,
                    "tipo_iva": producto.tipo_iva,
                    "concepto_id": concepto_id,
                },
            )
        else:
            # Sin concepto que lo referencie todavía: nace un básico nuevo,
            # con el precio de su tarifa preferente (o la más reciente
            # vigente), igual que calcularía `calculo.precio_referencia`.
            tarifa = conn.execute(
                sa.text(
                    "SELECT precio, descuento FROM presupuestos.precio_suministro "
                    "WHERE producto_id = :producto_id AND organization_id = :org_id "
                    "AND (vigente_hasta IS NULL OR vigente_hasta >= CURRENT_DATE) "
                    "ORDER BY es_preferente DESC, vigente_desde DESC LIMIT 1"
                ),
                {"producto_id": producto.id, "org_id": producto.organization_id},
            ).first()
            precio = Decimal("0.00")
            if tarifa is not None:
                neto = _redondear(
                    tarifa.precio * (Decimal("100") - tarifa.descuento) / Decimal("100"),
                    _CUATRO_DECIMALES,
                )
                precio = _redondear(neto, _DOS_DECIMALES)

            codigo = producto.codigo
            choca = conn.execute(
                sa.text(
                    "SELECT 1 FROM presupuestos.concepto "
                    "WHERE organization_id = :org_id AND codigo = :codigo"
                ),
                {"org_id": producto.organization_id, "codigo": codigo},
            ).first()
            if choca is not None:
                codigo = f"{codigo}-P"

            concepto_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO presupuestos.concepto ("
                    "id, organization_id, codigo, tipo, naturaleza, unidad, resumen, "
                    "texto, precio, origen_precio, fecha_precio, costes_indirectos, "
                    "ean, familia_id, precio_venta, tipo_iva, "
                    "activo, origen_dato, atributos, created_at, updated_at"
                    ") VALUES ("
                    ":id, :organization_id, :codigo, 'basico', :naturaleza, :unidad, :resumen, "
                    "NULL, :precio, 'producto', NULL, NULL, "
                    ":ean, :familia_id, :precio_venta, :tipo_iva, "
                    ":activo, :origen_dato, CAST(:atributos AS jsonb), now(), now()"
                    ")"
                ),
                {
                    "id": concepto_id,
                    "organization_id": producto.organization_id,
                    "codigo": codigo,
                    "naturaleza": producto.tipo,
                    "unidad": producto.unidad,
                    "resumen": producto.resumen,
                    "precio": precio,
                    "ean": producto.ean,
                    "familia_id": producto.familia_id,
                    "precio_venta": producto.precio_venta,
                    "tipo_iva": producto.tipo_iva,
                    "activo": producto.activo,
                    "origen_dato": producto.origen_dato,
                    "atributos": producto.atributos,
                },
            )

        concepto_de_producto[producto.id] = concepto_id

    # --- 4. Repuntar precio_suministro y albaran_linea al concepto ---
    for producto_id, concepto_id in concepto_de_producto.items():
        conn.execute(
            sa.text(
                "UPDATE presupuestos.precio_suministro SET producto_id = :concepto_id "
                "WHERE producto_id = :producto_id"
            ),
            {"concepto_id": concepto_id, "producto_id": producto_id},
        )
        conn.execute(
            sa.text(
                "UPDATE compras.albaran_linea SET producto_id = :concepto_id "
                "WHERE producto_id = :producto_id"
            ),
            {"concepto_id": concepto_id, "producto_id": producto_id},
        )

    # --- 5. Retirar producto_id de concepto ---
    op.drop_constraint(
        op.f("fk_concepto_producto_id_producto"), "concepto", schema="presupuestos", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_presupuestos_concepto_producto_id"), table_name="concepto", schema="presupuestos"
    )
    op.drop_column("concepto", "producto_id", schema="presupuestos")

    # --- 6. precio_suministro.producto_id -> concepto_id (la FK vieja ya se
    #     quitó en el paso 3; aquí solo renombra y añade la nueva) ---
    op.alter_column(
        "precio_suministro", "producto_id", new_column_name="concepto_id", schema="presupuestos"
    )
    op.create_foreign_key(
        op.f("fk_precio_suministro_concepto_id_concepto"),
        "precio_suministro", "concepto", ["concepto_id"], ["id"],
        source_schema="presupuestos", referent_schema="presupuestos",
        ondelete="CASCADE",
    )

    # --- 7. albaran_linea.producto_id -> concepto_id (misma razón) ---
    op.alter_column(
        "albaran_linea", "producto_id", new_column_name="concepto_id", schema="compras"
    )
    op.create_foreign_key(
        op.f("fk_albaran_linea_concepto_id_concepto"),
        "albaran_linea", "concepto", ["concepto_id"], ["id"],
        source_schema="compras", referent_schema="presupuestos",
        ondelete="SET NULL",
    )

    # --- 8. Retirar el server_default temporal de tipo_iva ---
    op.alter_column("concepto", "tipo_iva", server_default=None, schema="presupuestos")

    # --- 9. catalogo.producto ya no lo referencia nadie: fuera ---
    op.drop_table("producto", schema="catalogo")
    op.execute("DROP SCHEMA catalogo")

    # --- 10. Histórico de precios: una fila por cada cambio real de precio ---
    op.create_table(
        "historico_precio_concepto",
        sa.Column("concepto_id", sa.UUID(), nullable=False),
        sa.Column("precio", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "origen_precio",
            sa.Enum(
                "manual", "producto", "descomposicion",
                name="origen_precio", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["concepto_id"], ["presupuestos.concepto.id"],
            name=op.f("fk_historico_precio_concepto_concepto_id_concepto"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_historico_precio_concepto_organization_id_organization"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_historico_precio_concepto")),
        schema="presupuestos",
    )
    op.create_index(
        op.f("ix_presupuestos_historico_precio_concepto_organization_id"),
        "historico_precio_concepto", ["organization_id"], unique=False, schema="presupuestos",
    )
    op.create_index(
        "ix_presupuestos_historico_precio_concepto_concepto",
        "historico_precio_concepto", ["organization_id", "concepto_id", "fecha"],
        unique=False, schema="presupuestos",
    )
    activar_rls("presupuestos", "historico_precio_concepto")


def downgrade() -> None:
    """Reversión best-effort: no reconstituye `catalogo.Producto` ni separa de
    vuelta los productos fusionados en un concepto ya existente — no hay forma
    no ambigua de saber qué parte de un concepto fusionado era "el producto".
    Solo deshace lo estructuralmente reversible: el histórico, las columnas
    nuevas de concepto y la ubicación de familia/precio_suministro."""
    desactivar_rls("presupuestos", "historico_precio_concepto")
    op.drop_table("historico_precio_concepto", schema="presupuestos")

    op.execute("CREATE SCHEMA IF NOT EXISTS catalogo")

    op.drop_constraint(
        op.f("fk_albaran_linea_concepto_id_concepto"), "albaran_linea", schema="compras", type_="foreignkey"
    )
    op.alter_column(
        "albaran_linea", "concepto_id", new_column_name="producto_id", schema="compras"
    )

    op.drop_constraint(
        op.f("fk_precio_suministro_concepto_id_concepto"),
        "precio_suministro", schema="presupuestos", type_="foreignkey",
    )
    op.alter_column(
        "precio_suministro", "concepto_id", new_column_name="producto_id", schema="presupuestos"
    )

    op.add_column(
        "concepto",
        sa.Column("producto_id", sa.UUID(), nullable=True),
        schema="presupuestos",
    )
    op.create_index(
        op.f("ix_presupuestos_concepto_producto_id"), "concepto", ["producto_id"],
        unique=False, schema="presupuestos",
    )

    op.drop_constraint(
        op.f("fk_concepto_familia_id_familia"), "concepto", schema="presupuestos", type_="foreignkey"
    )
    op.drop_index(op.f("ix_presupuestos_concepto_familia_id"), table_name="concepto", schema="presupuestos")
    op.drop_column("concepto", "tipo_iva", schema="presupuestos")
    op.drop_column("concepto", "precio_venta", schema="presupuestos")
    op.drop_column("concepto", "familia_id", schema="presupuestos")
    op.drop_column("concepto", "ean", schema="presupuestos")

    op.execute(
        "ALTER INDEX presupuestos.uq_presupuestos_precio_suministro_preferente "
        "RENAME TO uq_catalogo_precio_suministro_preferente"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_presupuestos_precio_suministro_proveedor "
        "RENAME TO ix_catalogo_precio_suministro_proveedor"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_presupuestos_precio_suministro_concepto "
        "RENAME TO ix_catalogo_precio_suministro_producto"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_presupuestos_precio_suministro_organization_id "
        "RENAME TO ix_catalogo_precio_suministro_organization_id"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_presupuestos_familia_parent_id "
        "RENAME TO ix_catalogo_familia_parent_id"
    )
    op.execute(
        "ALTER INDEX presupuestos.ix_presupuestos_familia_organization_id "
        "RENAME TO ix_catalogo_familia_organization_id"
    )

    op.execute("ALTER TABLE presupuestos.precio_suministro SET SCHEMA catalogo")
    op.execute("ALTER TABLE presupuestos.familia SET SCHEMA catalogo")

    op.create_table(
        "producto",
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "material", "mano_obra", "maquinaria", "servicio", "otro",
                name="tipo_producto", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("familia_id", sa.UUID(), nullable=True),
        sa.Column("resumen", sa.String(length=250), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("unidad", sa.String(length=10), nullable=False),
        sa.Column(
            "tipo_iva",
            sa.Enum(
                "general", "reducido", "superreducido", "exento",
                name="tipo_iva", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("precio_venta", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("ean", sa.String(length=14), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column(
            "origen_dato",
            sa.Enum(
                "manual", "fiebdc3", "ia", "importado",
                name="origen_dato", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("atributos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["familia_id"], ["catalogo.familia.id"],
            name=op.f("fk_producto_familia_id_familia"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["core.organization.id"],
            name=op.f("fk_producto_organization_id_organization"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_producto")),
        sa.UniqueConstraint("organization_id", "codigo", name="producto_codigo_unique"),
        schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_producto_familia_id"), "producto", ["familia_id"],
        unique=False, schema="catalogo",
    )
    op.create_index(
        op.f("ix_catalogo_producto_organization_id"), "producto", ["organization_id"],
        unique=False, schema="catalogo",
    )
    op.create_index(
        "ix_catalogo_producto_resumen", "producto", ["organization_id", "resumen"],
        unique=False, schema="catalogo",
    )
    op.create_index(
        "ix_catalogo_producto_tipo", "producto", ["organization_id", "tipo"],
        unique=False, schema="catalogo",
    )
    conceder_privilegios_app("catalogo")
