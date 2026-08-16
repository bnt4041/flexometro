"""compartir maestros entre organizaciones de una cuenta

Revision ID: 63821d58ff8a
Revises: 8fc5b0cfbcbf
Create Date: 2026-08-12 19:03:29.127905

Fase 15: `Cuenta.compartir_maestros` (off por defecto) y la política RLS de
los maestros compartibles — terceros, catálogo y cuadro de precios — pasa de
"solo mi organización" a "mi organización, o también las hermanas de mi
cuenta si compartir_maestros está activo". Documentos fiscales/operativos
(presupuesto, capítulo, partida, línea de medición y todo lo de obras/
compras/facturación) NO se tocan: siguen aislados por organización siempre,
sin excepción — atados por ley a un CIF concreto.

Depende de las cabezas de terceros/catalogo/presupuestos porque altera
tablas de esos tres schemas, no solo el propio.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import convertir_a_rls_maestro, revertir_rls_maestro

revision: str = '63821d58ff8a'
down_revision: str | None = '8fc5b0cfbcbf'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = ('terceros_0002', 'catalogo_0002', 'presupuestos_0004')

# Documentos fiscales/operativos deliberadamente NO incluidos aquí, ver
# docstring del módulo.
_TABLAS_MAESTRO: list[tuple[str, str]] = [
    ('terceros', 'tercero'),
    ('terceros', 'contacto'),
    ('catalogo', 'producto'),
    ('catalogo', 'familia'),
    ('catalogo', 'precio_suministro'),
    ('presupuestos', 'concepto'),
    ('presupuestos', 'descomposicion'),
]


def upgrade() -> None:
    op.add_column(
        'cuenta',
        sa.Column('compartir_maestros', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema='core',
    )
    op.alter_column('cuenta', 'compartir_maestros', server_default=None, schema='core')

    for schema, tabla in _TABLAS_MAESTRO:
        convertir_a_rls_maestro(schema, tabla)


def downgrade() -> None:
    for schema, tabla in reversed(_TABLAS_MAESTRO):
        revertir_rls_maestro(schema, tabla)

    op.drop_column('cuenta', 'compartir_maestros', schema='core')
