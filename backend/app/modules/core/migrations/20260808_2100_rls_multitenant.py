"""core: aislamiento entre organizaciones con RLS

Activa Row Level Security en todas las tablas de negocio. A partir de aquí, el
aislamiento entre organizaciones no depende de que cada consulta se acuerde de
filtrar por `organization_id`: lo impone PostgreSQL. Un `select` que se olvide
del filtro devuelve las filas de la organización activa y ninguna más.

La organización activa se publica en la conexión como `app.organization_id`
desde `get_session`, con `set_config(..., true)`, que es local a la transacción
y por tanto no se filtra entre peticiones que comparten conexión del pool.

`core.organization` queda fuera a propósito: hay que poder leerla para resolver
a qué organización pertenece quien acaba de autenticarse, justo antes de que
exista contexto.

Revision ID: core_0002
Revises: core_0001
Create Date: 2026-08-08
"""
from collections.abc import Sequence

from alembic import op

revision: str = "core_0002"
down_revision: str | None = "core_0001"
branch_labels: str | Sequence[str] | None = None
# Las tablas viven en las otras ramas, así que esta migración va después.
depends_on: str | Sequence[str] | None = ("terceros", "catalogo", "presupuestos")

TABLAS = [
    ("core", "organization_module"),
    ("terceros", "tercero"),
    ("terceros", "contacto"),
    ("catalogo", "familia"),
    ("catalogo", "producto"),
    ("catalogo", "precio_suministro"),
    ("presupuestos", "concepto"),
    ("presupuestos", "descomposicion"),
    ("presupuestos", "presupuesto"),
    ("presupuestos", "capitulo"),
    ("presupuestos", "partida"),
    ("presupuestos", "linea_medicion"),
]

POLITICA = "aislamiento_organizacion"

# NULLIF: sin contexto, `current_setting(..., true)` puede devolver NULL o
# cadena vacía según cómo se dejara la sesión. Con NULLIF los dos casos acaban
# en NULL, la comparación es NULL y no se ve ninguna fila. Fallar cerrado.
CONDICION = (
    "organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid"
)


def upgrade() -> None:
    for schema, tabla in TABLAS:
        completo = f"{schema}.{tabla}"
        op.execute(f"ALTER TABLE {completo} ENABLE ROW LEVEL SECURITY")
        # FORCE: sin esto el propietario de la tabla se salta sus propias
        # políticas, y la aplicación se conecta justo con ese usuario.
        op.execute(f"ALTER TABLE {completo} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {POLITICA} ON {completo}
                USING ({CONDICION})
                WITH CHECK ({CONDICION})
            """
        )


def downgrade() -> None:
    for schema, tabla in TABLAS:
        completo = f"{schema}.{tabla}"
        op.execute(f"DROP POLICY IF EXISTS {POLITICA} ON {completo}")
        op.execute(f"ALTER TABLE {completo} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {completo} DISABLE ROW LEVEL SECURITY")
