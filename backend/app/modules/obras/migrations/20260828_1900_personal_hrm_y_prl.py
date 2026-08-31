"""obras: ficha laboral y de PRL del personal

`Personal` tenía lo justo para imputar coste a una obra (código, nombre,
categoría, coste/hora). Para llevar el HRM y la prevención hace falta el resto
de la ficha: identificación, contrato, y lo que exigen la Ley 31/1995 y el
convenio del sector (formación, aptitud médica, EPIs, TPC).

Todas las columnas son NULL: hay plantillas ya cargadas y ninguna podría
rellenar esto de golpe. El módulo PRL avisa de lo que falta en vez de impedir
guardar.

Sobre datos personales: se guarda el VEREDICTO de aptitud médica, nunca el
resultado clínico. El dato de salud es categoría especial del art. 9 RGPD y la
empresa no puede tratarlo — solo necesita saber si la persona puede o no
desempeñar el puesto.

Revision ID: obras_0007
Revises: obras_0006
Create Date: 2026-08-28
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "obras_0007"
down_revision: str | None = "obras_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNAS = [
    # Identificación
    ("nif", sa.String(length=20)),
    ("fecha_nacimiento", sa.Date()),
    ("nacionalidad", sa.String(length=60)),
    ("telefono", sa.String(length=40)),
    ("email", sa.String(length=200)),
    ("direccion", sa.String(length=200)),
    ("codigo_postal", sa.String(length=10)),
    ("poblacion", sa.String(length=120)),
    ("provincia", sa.String(length=80)),
    # Emergencia
    ("contacto_emergencia", sa.String(length=160)),
    ("telefono_emergencia", sa.String(length=40)),
    # Laboral
    ("naf", sa.String(length=20)),
    ("iban", sa.String(length=34)),
    ("fecha_alta", sa.Date()),
    ("fecha_fin_contrato", sa.Date()),
    ("fecha_baja", sa.Date()),
    ("grupo_cotizacion", sa.String(length=10)),
    ("convenio", sa.String(length=120)),
    ("jornada_horas_semana", sa.Numeric(5, 2)),
    ("salario_bruto_anual", sa.Numeric(12, 2)),
    # PRL
    ("tpc_numero", sa.String(length=40)),
    ("tpc_caducidad", sa.Date()),
    ("formacion_prl_horas", sa.Integer()),
    ("formacion_prl_fecha", sa.Date()),
    ("fecha_reconocimiento_medico", sa.Date()),
    ("proximo_reconocimiento", sa.Date()),
    ("epis_entregados", sa.Text()),
    ("fecha_entrega_epis", sa.Date()),
    ("informacion_riesgos_fecha", sa.Date()),
]


def upgrade() -> None:
    for nombre, tipo in _COLUMNAS:
        op.add_column("personal", sa.Column(nombre, tipo, nullable=True), schema="obras")

    # Los dos enumerados. `native_enum=False` en todo el proyecto: es un
    # VARCHAR, así que añadir valores después no exige un ALTER TYPE.
    op.add_column(
        "personal",
        sa.Column(
            "tipo_contrato",
            sa.Enum(
                "indefinido", "temporal", "fijo_discontinuo", "obra_y_servicio",
                "formacion", "practicas", "autonomo", "otro",
                name="tipo_contrato_laboral", native_enum=False, length=32,
            ),
            nullable=True,
        ),
        schema="obras",
    )
    op.add_column(
        "personal",
        sa.Column(
            "aptitud_medica",
            sa.Enum(
                "apto", "apto_con_restricciones", "no_apto", "pendiente",
                name="aptitud_medica", native_enum=False, length=32,
            ),
            nullable=True,
        ),
        schema="obras",
    )
    op.add_column(
        "personal",
        sa.Column(
            "es_recurso_preventivo", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        schema="obras",
    )


def downgrade() -> None:
    for nombre in (
        "es_recurso_preventivo",
        "aptitud_medica",
        "tipo_contrato",
        *[c[0] for c in reversed(_COLUMNAS)],
    ):
        op.drop_column("personal", nombre, schema="obras")
