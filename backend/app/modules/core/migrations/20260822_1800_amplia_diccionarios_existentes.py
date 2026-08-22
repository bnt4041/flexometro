"""amplia diccionarios existentes

Revision ID: f69c3a8e1d52
Revises: e58b2d0f4a73
Create Date: 2026-08-22 18:00:00

Fase 41: se completan con más valores los diccionarios que ya tenía cada
cuenta (unidad_medida, forma_juridica, tratamiento, cargo) — no son
diccionarios de "sistema" (`forma_pago` sí lo es: sus claves las restringe
de verdad el enum `FormaPago` de `terceros/models.py`, así que ESE no se
toca aquí, se dejaría con opciones que la app rechazaría al guardarlas).
Mismo patrón que las Fases 18/20: sembrar cada cuenta existente; las cuentas
nuevas ya reciben este juego completo desde `diccionario_seeds.py`.
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f69c3a8e1d52'
down_revision: str | None = 'e58b2d0f4a73'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNIDADES_MEDIDA_NUEVAS: list[tuple[str, str]] = [
    ('km', 'Kilómetro'), ('cm', 'Centímetro'), ('mm', 'Milímetro'), ('g', 'Gramo'),
    ('ha', 'Hectárea'), ('dia', 'Día'), ('mes', 'Mes'), ('jornada', 'Jornada'),
    ('viaje', 'Viaje'), ('pct', 'Porcentaje'),
]

FORMAS_JURIDICAS_NUEVAS: list[tuple[str, str]] = [
    ('SLNE', 'Sociedad Limitada Nueva Empresa'), ('UTE', 'Unión Temporal de Empresas'),
    ('FUNDACION', 'Fundación'), ('AIE', 'Agrupación de Interés Económico'),
]

TRATAMIENTOS_NUEVOS: list[tuple[str, str]] = [
    ('ing', 'Ing.'), ('arq', 'Arq.'), ('prof', 'Prof.'),
]

CARGOS_NUEVOS: list[tuple[str, str]] = [
    ('delineante', 'Delineante'), ('topografo', 'Topógrafo'),
    ('prevencionista', 'Técnico de prevención'), ('subcontratista', 'Subcontratista'),
    ('oficial_1', 'Oficial de 1ª'), ('oficial_2', 'Oficial de 2ª'),
    ('peon', 'Peón'), ('capataz', 'Capataz'),
    ('project_manager', 'Project manager'), ('calidad', 'Técnico de calidad'),
    ('medioambiente', 'Técnico de medio ambiente'), ('almacen', 'Responsable de almacén'),
]


def upgrade() -> None:
    conn = op.get_bind()
    cuenta_ids = [fila[0] for fila in conn.execute(sa.text('SELECT id FROM core.cuenta')).fetchall()]
    for cuenta_id in cuenta_ids:
        orden_inicial = _siguiente_orden(conn, cuenta_id, 'unidad_medida')
        _sembrar(conn, cuenta_id, tipo='unidad_medida', entradas=UNIDADES_MEDIDA_NUEVAS, orden_inicial=orden_inicial)

        orden_inicial = _siguiente_orden(conn, cuenta_id, 'forma_juridica')
        _sembrar(conn, cuenta_id, tipo='forma_juridica', entradas=FORMAS_JURIDICAS_NUEVAS, orden_inicial=orden_inicial)

        orden_inicial = _siguiente_orden(conn, cuenta_id, 'tratamiento')
        _sembrar(conn, cuenta_id, tipo='tratamiento', entradas=TRATAMIENTOS_NUEVOS, orden_inicial=orden_inicial)

        orden_inicial = _siguiente_orden(conn, cuenta_id, 'cargo')
        _sembrar(conn, cuenta_id, tipo='cargo', entradas=CARGOS_NUEVOS, orden_inicial=orden_inicial)


def _siguiente_orden(conn, cuenta_id: uuid.UUID, tipo: str) -> int:
    maximo = conn.execute(
        sa.text(
            'SELECT COALESCE(MAX(orden), -1) FROM core.entrada_diccionario '
            'WHERE cuenta_id = :cuenta_id AND tipo = :tipo'
        ),
        {'cuenta_id': cuenta_id, 'tipo': tipo},
    ).scalar()
    return maximo + 1


def _sembrar(conn, cuenta_id: uuid.UUID, *, tipo: str, entradas: list[tuple[str, str]], orden_inicial: int) -> None:
    for i, (clave, etiqueta) in enumerate(entradas):
        # `ON CONFLICT DO NOTHING`: si esta migración se llegara a re-ejecutar
        # sobre una cuenta que ya tiene la clave (p. ej. una sembrada de
        # nuevas ya con el juego completo), no revienta por la clave única.
        conn.execute(
            sa.text(
                'INSERT INTO core.entrada_diccionario '
                '(id, cuenta_id, tipo, clave, etiqueta, activo, orden) '
                'VALUES (:id, :cuenta_id, :tipo, :clave, :etiqueta, true, :orden) '
                'ON CONFLICT (cuenta_id, tipo, clave) DO NOTHING'
            ),
            {
                'id': uuid.uuid4(),
                'cuenta_id': cuenta_id,
                'tipo': tipo,
                'clave': clave,
                'etiqueta': etiqueta,
                'orden': orden_inicial + i,
            },
        )


def downgrade() -> None:
    claves_por_tipo = {
        'unidad_medida': [c for c, _ in UNIDADES_MEDIDA_NUEVAS],
        'forma_juridica': [c for c, _ in FORMAS_JURIDICAS_NUEVAS],
        'tratamiento': [c for c, _ in TRATAMIENTOS_NUEVOS],
        'cargo': [c for c, _ in CARGOS_NUEVOS],
    }
    conn = op.get_bind()
    for tipo, claves in claves_por_tipo.items():
        conn.execute(
            sa.text('DELETE FROM core.entrada_diccionario WHERE tipo = :tipo AND clave = ANY(:claves)'),
            {'tipo': tipo, 'claves': claves},
        )
