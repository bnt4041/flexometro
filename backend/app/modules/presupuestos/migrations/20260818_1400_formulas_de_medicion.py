"""formulas de medicion

Revision ID: presupuestos_0009
Revises: presupuestos_0008
Create Date: 2026-08-18 14:00:00

Fase 37: fórmulas reutilizables para medir (área de triángulo, volumen de
cilindro...). Por cuenta y sin RLS, igual que `core.entrada_diccionario` y
`campos_libres.definicion`: son vocabulario de trabajo, no datos de negocio de
una organización concreta.

Se siembra un juego inicial en cada cuenta existente, mismo patrón que la
migración de diccionarios de la Fase 20. La línea de medición guarda además una
copia congelada de la expresión, para que editar la fórmula del catálogo no
cambie lo que ya estaba medido.
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "presupuestos_0009"
down_revision: str | None = "presupuestos_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nombre, expresión, descripción)
FORMULAS: list[tuple[str, str, str]] = [
    ("Área de triángulo", "base * altura / 2", "Media base por altura"),
    ("Área de círculo", "pi * radio ** 2", "Superficie de un círculo"),
    (
        "Área de trapecio",
        "(base_mayor + base_menor) / 2 * altura",
        "Semisuma de las bases por la altura",
    ),
    ("Perímetro de círculo", "2 * pi * radio", "Longitud de la circunferencia"),
    (
        "Área de corona circular",
        "pi * (radio_exterior ** 2 - radio_interior ** 2)",
        "Anillo entre dos círculos concéntricos",
    ),
    (
        "Área de sector circular",
        "pi * radio ** 2 * angulo / 360",
        "Porción de círculo según el ángulo en grados",
    ),
    ("Volumen de prisma", "largo * ancho * alto", "Volumen de una caja"),
    ("Volumen de cilindro", "pi * radio ** 2 * altura", "Volumen de un cilindro"),
    (
        "Hipotenusa (Pitágoras)",
        "sqrt(cateto_a ** 2 + cateto_b ** 2)",
        "Diagonal a partir de los dos catetos",
    ),
    (
        "Superficie de cubierta inclinada",
        "largo * ancho / cos(radians(pendiente))",
        "Corrige la proyección en planta por la pendiente en grados",
    ),
]


def upgrade() -> None:
    op.create_table(
        "formula_medicion",
        sa.Column("cuenta_id", sa.UUID(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("expresion", sa.String(length=500), nullable=False),
        sa.Column("descripcion", sa.String(length=250), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["cuenta_id"],
            ["core.cuenta.id"],
            name=op.f("fk_formula_medicion_cuenta_id_cuenta"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formula_medicion")),
        sa.UniqueConstraint("cuenta_id", "nombre", name="formula_medicion_nombre_unique"),
        schema="presupuestos",
    )

    op.add_column(
        "linea_medicion",
        sa.Column("formula_id", sa.UUID(), nullable=True),
        schema="presupuestos",
    )
    op.add_column(
        "linea_medicion",
        sa.Column("formula_expresion", sa.String(length=500), nullable=True),
        schema="presupuestos",
    )
    op.add_column(
        "linea_medicion",
        sa.Column(
            "formula_valores",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        schema="presupuestos",
    )
    op.create_foreign_key(
        op.f("fk_linea_medicion_formula_id_formula_medicion"),
        "linea_medicion",
        "formula_medicion",
        ["formula_id"],
        ["id"],
        source_schema="presupuestos",
        referent_schema="presupuestos",
        ondelete="SET NULL",
    )

    # Sembrar el juego inicial en cada cuenta que ya existe.
    conn = op.get_bind()
    cuentas = list(conn.execute(sa.text("SELECT id FROM core.cuenta")).scalars())
    for cuenta_id in cuentas:
        for orden, (nombre, expresion, descripcion) in enumerate(FORMULAS):
            conn.execute(
                sa.text(
                    "INSERT INTO presupuestos.formula_medicion "
                    "(id, cuenta_id, nombre, expresion, descripcion, orden, activa) "
                    "VALUES (:id, :cuenta_id, :nombre, :expresion, :descripcion, :orden, true)"
                ),
                {
                    "id": uuid.uuid4(),
                    "cuenta_id": cuenta_id,
                    "nombre": nombre,
                    "expresion": expresion,
                    "descripcion": descripcion,
                    "orden": orden,
                },
            )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_linea_medicion_formula_id_formula_medicion"),
        "linea_medicion",
        type_="foreignkey",
        schema="presupuestos",
    )
    op.drop_column("linea_medicion", "formula_valores", schema="presupuestos")
    op.drop_column("linea_medicion", "formula_expresion", schema="presupuestos")
    op.drop_column("linea_medicion", "formula_id", schema="presupuestos")
    op.drop_table("formula_medicion", schema="presupuestos")
