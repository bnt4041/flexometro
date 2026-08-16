"""diccionarios adicionales estilo dolibarr

Revision ID: 5eef0f540e95b
Revises: bf130a64f9c2
Create Date: 2026-08-16 09:33:49.448927

Fase 20: cinco categorías nuevas de `core.entrada_diccionario` (provincia,
unidad_medida, forma_juridica, tratamiento, cargo) — ninguna requiere DDL,
`tipo` ya es un `character varying(32)` sin CHECK constraint (ver
`app/core/enums.py::enum_column`: el enum solo se valida en Python/Pydantic,
no en la base de datos). Solo hace falta sembrar cada cuenta existente, igual
que la migración de Fase 18.
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '5eef0f540e95b'
down_revision: str | None = 'bf130a64f9c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROVINCIAS: list[tuple[str, str]] = [
    ('01', 'Araba/Álava'), ('02', 'Albacete'), ('03', 'Alicante/Alacant'), ('04', 'Almería'),
    ('05', 'Ávila'), ('06', 'Badajoz'), ('07', 'Balears, Illes'), ('08', 'Barcelona'),
    ('09', 'Burgos'), ('10', 'Cáceres'), ('11', 'Cádiz'), ('12', 'Castellón/Castelló'),
    ('13', 'Ciudad Real'), ('14', 'Córdoba'), ('15', 'Coruña, A'), ('16', 'Cuenca'),
    ('17', 'Girona'), ('18', 'Granada'), ('19', 'Guadalajara'), ('20', 'Gipuzkoa'),
    ('21', 'Huelva'), ('22', 'Huesca'), ('23', 'Jaén'), ('24', 'León'),
    ('25', 'Lleida'), ('26', 'Rioja, La'), ('27', 'Lugo'), ('28', 'Madrid'),
    ('29', 'Málaga'), ('30', 'Murcia'), ('31', 'Navarra'), ('32', 'Ourense'),
    ('33', 'Asturias'), ('34', 'Palencia'), ('35', 'Palmas, Las'), ('36', 'Pontevedra'),
    ('37', 'Salamanca'), ('38', 'Santa Cruz de Tenerife'), ('39', 'Cantabria'), ('40', 'Segovia'),
    ('41', 'Sevilla'), ('42', 'Soria'), ('43', 'Tarragona'), ('44', 'Teruel'),
    ('45', 'Toledo'), ('46', 'Valencia/València'), ('47', 'Valladolid'), ('48', 'Bizkaia'),
    ('49', 'Zamora'), ('50', 'Zaragoza'), ('51', 'Ceuta'), ('52', 'Melilla'),
]

UNIDADES_MEDIDA: list[tuple[str, str]] = [
    ('ud', 'Unidad'), ('m', 'Metro'), ('m2', 'Metro cuadrado'), ('m3', 'Metro cúbico'),
    ('kg', 'Kilogramo'), ('h', 'Hora'), ('l', 'Litro'), ('ml', 'Metro lineal'),
    ('t', 'Tonelada'), ('pa', 'Partida alzada'),
]

FORMAS_JURIDICAS: list[tuple[str, str]] = [
    ('AUTONOMO', 'Autónomo'), ('SL', 'Sociedad Limitada'), ('SLU', 'Sociedad Limitada Unipersonal'),
    ('SA', 'Sociedad Anónima'), ('CB', 'Comunidad de Bienes'), ('SC', 'Sociedad Civil'),
    ('SCOOP', 'Sociedad Cooperativa'), ('SAT', 'Sociedad Agraria de Transformación'),
    ('ONG', 'Asociación / ONG'),
]

TRATAMIENTOS: list[tuple[str, str]] = [
    ('sr', 'Sr.'), ('sra', 'Sra.'), ('srta', 'Srta.'), ('don', 'Don'),
    ('dona', 'Doña'), ('dr', 'Dr.'), ('dra', 'Dra.'),
]

CARGOS: list[tuple[str, str]] = [
    ('jefe_obra', 'Jefe de obra'), ('arquitecto', 'Arquitecto'),
    ('aparejador', 'Aparejador / Arquitecto técnico'), ('ingeniero', 'Ingeniero'),
    ('comercial', 'Comercial'), ('administracion', 'Administración'),
    ('gerente', 'Gerente'), ('encargado', 'Encargado'),
    ('propiedad', 'Propiedad'), ('contable', 'Contable'),
]


def upgrade() -> None:
    conn = op.get_bind()
    cuenta_ids = [fila[0] for fila in conn.execute(sa.text('SELECT id FROM core.cuenta')).fetchall()]
    for cuenta_id in cuenta_ids:
        _sembrar(conn, cuenta_id, tipo='provincia', entradas=PROVINCIAS)
        _sembrar(conn, cuenta_id, tipo='unidad_medida', entradas=UNIDADES_MEDIDA)
        _sembrar(conn, cuenta_id, tipo='forma_juridica', entradas=FORMAS_JURIDICAS)
        _sembrar(conn, cuenta_id, tipo='tratamiento', entradas=TRATAMIENTOS)
        _sembrar(conn, cuenta_id, tipo='cargo', entradas=CARGOS)


def _sembrar(conn, cuenta_id: uuid.UUID, *, tipo: str, entradas: list[tuple[str, str]]) -> None:
    for orden, (clave, etiqueta) in enumerate(entradas):
        conn.execute(
            sa.text(
                'INSERT INTO core.entrada_diccionario '
                '(id, cuenta_id, tipo, clave, etiqueta, activo, orden) '
                'VALUES (:id, :cuenta_id, :tipo, :clave, :etiqueta, true, :orden)'
            ),
            {
                'id': uuid.uuid4(),
                'cuenta_id': cuenta_id,
                'tipo': tipo,
                'clave': clave,
                'etiqueta': etiqueta,
                'orden': orden,
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM core.entrada_diccionario WHERE tipo IN "
        "('provincia', 'unidad_medida', 'forma_juridica', 'tratamiento', 'cargo')"
    )
