"""diccionario de referencia

Revision ID: 1457b7e50efd
Revises: cc3da38b179b
Create Date: 2026-08-16 08:19:44.262280

Fase 18: siembra cada cuenta ya existente con el diccionario de países (ISO
3166-1 alfa-2, nombre en español) y de formas de pago (mismas claves que el
enum `FormaPago` de `terceros/models.py`, que sigue siendo quien de verdad
restringe qué valor acepta la base de datos en `Tercero.forma_pago`/
`CobroFactura.forma_pago` — esto solo aporta etiqueta, orden y activación
editables por el tenant).
"""
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '1457b7e50efd'
down_revision: str | None = 'cc3da38b179b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PAISES: list[tuple[str, str]] = [
    ('ES', 'España'), ('PT', 'Portugal'), ('FR', 'Francia'), ('DE', 'Alemania'),
    ('IT', 'Italia'), ('GB', 'Reino Unido'), ('IE', 'Irlanda'), ('NL', 'Países Bajos'),
    ('BE', 'Bélgica'), ('LU', 'Luxemburgo'), ('CH', 'Suiza'), ('AT', 'Austria'),
    ('DK', 'Dinamarca'), ('SE', 'Suecia'), ('NO', 'Noruega'), ('FI', 'Finlandia'),
    ('IS', 'Islandia'), ('PL', 'Polonia'), ('CZ', 'República Checa'), ('SK', 'Eslovaquia'),
    ('HU', 'Hungría'), ('RO', 'Rumanía'), ('BG', 'Bulgaria'), ('GR', 'Grecia'),
    ('HR', 'Croacia'), ('SI', 'Eslovenia'), ('EE', 'Estonia'), ('LV', 'Letonia'),
    ('LT', 'Lituania'), ('MT', 'Malta'), ('CY', 'Chipre'), ('AD', 'Andorra'),
    ('MC', 'Mónaco'), ('SM', 'San Marino'), ('VA', 'Ciudad del Vaticano'), ('LI', 'Liechtenstein'),
    ('AL', 'Albania'), ('MK', 'Macedonia del Norte'), ('ME', 'Montenegro'), ('RS', 'Serbia'),
    ('BA', 'Bosnia y Herzegovina'), ('XK', 'Kosovo'), ('MD', 'Moldavia'), ('UA', 'Ucrania'),
    ('BY', 'Bielorrusia'), ('RU', 'Rusia'),
    ('US', 'Estados Unidos'), ('CA', 'Canadá'), ('MX', 'México'),
    ('GT', 'Guatemala'), ('BZ', 'Belice'), ('HN', 'Honduras'), ('SV', 'El Salvador'),
    ('NI', 'Nicaragua'), ('CR', 'Costa Rica'), ('PA', 'Panamá'), ('CU', 'Cuba'),
    ('DO', 'República Dominicana'), ('HT', 'Haití'), ('JM', 'Jamaica'), ('BS', 'Bahamas'),
    ('TT', 'Trinidad y Tobago'), ('BB', 'Barbados'),
    ('CO', 'Colombia'), ('VE', 'Venezuela'), ('EC', 'Ecuador'), ('PE', 'Perú'),
    ('BO', 'Bolivia'), ('PY', 'Paraguay'), ('UY', 'Uruguay'), ('AR', 'Argentina'),
    ('BR', 'Brasil'), ('CL', 'Chile'), ('GY', 'Guyana'), ('SR', 'Surinam'),
    ('MA', 'Marruecos'), ('DZ', 'Argelia'), ('TN', 'Túnez'), ('LY', 'Libia'),
    ('EG', 'Egipto'), ('SD', 'Sudán'), ('MR', 'Mauritania'), ('ML', 'Malí'),
    ('SN', 'Senegal'), ('GM', 'Gambia'), ('GW', 'Guinea-Bisáu'), ('GN', 'Guinea'),
    ('CI', 'Costa de Marfil'), ('GH', 'Ghana'), ('TG', 'Togo'), ('BJ', 'Benín'),
    ('NE', 'Níger'), ('NG', 'Nigeria'), ('CM', 'Camerún'), ('TD', 'Chad'),
    ('CF', 'República Centroafricana'), ('GA', 'Gabón'), ('CG', 'Congo'), ('CD', 'República Democrática del Congo'),
    ('GQ', 'Guinea Ecuatorial'), ('ST', 'Santo Tomé y Príncipe'), ('AO', 'Angola'), ('ZM', 'Zambia'),
    ('ZW', 'Zimbabue'), ('MZ', 'Mozambique'), ('MW', 'Malaui'), ('NA', 'Namibia'),
    ('BW', 'Botsuana'), ('ZA', 'Sudáfrica'), ('SZ', 'Esuatini'), ('LS', 'Lesoto'),
    ('MG', 'Madagascar'), ('MU', 'Mauricio'), ('SC', 'Seychelles'), ('KM', 'Comoras'),
    ('DJ', 'Yibuti'), ('SO', 'Somalia'), ('ET', 'Etiopía'), ('ER', 'Eritrea'),
    ('KE', 'Kenia'), ('UG', 'Uganda'), ('TZ', 'Tanzania'), ('RW', 'Ruanda'),
    ('BI', 'Burundi'), ('SS', 'Sudán del Sur'), ('BF', 'Burkina Faso'), ('LR', 'Liberia'),
    ('SL', 'Sierra Leona'), ('CV', 'Cabo Verde'), ('EH', 'Sahara Occidental'),
    ('TR', 'Turquía'), ('IL', 'Israel'), ('PS', 'Palestina'), ('LB', 'Líbano'),
    ('SY', 'Siria'), ('JO', 'Jordania'), ('IQ', 'Irak'), ('IR', 'Irán'),
    ('SA', 'Arabia Saudí'), ('YE', 'Yemen'), ('OM', 'Omán'), ('AE', 'Emiratos Árabes Unidos'),
    ('QA', 'Catar'), ('BH', 'Baréin'), ('KW', 'Kuwait'), ('GE', 'Georgia'),
    ('AM', 'Armenia'), ('AZ', 'Azerbaiyán'), ('KZ', 'Kazajistán'), ('UZ', 'Uzbekistán'),
    ('TM', 'Turkmenistán'), ('TJ', 'Tayikistán'), ('KG', 'Kirguistán'), ('AF', 'Afganistán'),
    ('PK', 'Pakistán'), ('IN', 'India'), ('NP', 'Nepal'), ('BT', 'Bután'),
    ('BD', 'Bangladés'), ('LK', 'Sri Lanka'), ('MV', 'Maldivas'), ('MM', 'Birmania'),
    ('TH', 'Tailandia'), ('LA', 'Laos'), ('KH', 'Camboya'), ('VN', 'Vietnam'),
    ('MY', 'Malasia'), ('SG', 'Singapur'), ('ID', 'Indonesia'), ('BN', 'Brunéi'),
    ('PH', 'Filipinas'), ('TL', 'Timor Oriental'), ('CN', 'China'), ('TW', 'Taiwán'),
    ('HK', 'Hong Kong'), ('MO', 'Macao'), ('MN', 'Mongolia'), ('KP', 'Corea del Norte'),
    ('KR', 'Corea del Sur'), ('JP', 'Japón'),
    ('AU', 'Australia'), ('NZ', 'Nueva Zelanda'), ('FJ', 'Fiyi'), ('PG', 'Papúa Nueva Guinea'),
    ('SB', 'Islas Salomón'), ('VU', 'Vanuatu'), ('WS', 'Samoa'), ('TO', 'Tonga'),
    ('KI', 'Kiribati'), ('FM', 'Micronesia'), ('MH', 'Islas Marshall'), ('PW', 'Palaos'), ('NR', 'Nauru'),
    ('GL', 'Groenlandia'),
]

FORMAS_PAGO: list[tuple[str, str]] = [
    ('transferencia', 'Transferencia'),
    ('domiciliado', 'Domiciliado'),
    ('pagare', 'Pagaré'),
    ('confirming', 'Confirming'),
    ('efectivo', 'Efectivo'),
    ('tarjeta', 'Tarjeta'),
]


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('entrada_diccionario',
    sa.Column('cuenta_id', sa.UUID(), nullable=False),
    sa.Column('tipo', sa.Enum('pais', 'forma_pago', name='tipo_diccionario', native_enum=False, length=32), nullable=False),
    sa.Column('clave', sa.String(length=64), nullable=False),
    sa.Column('etiqueta', sa.String(length=120), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['cuenta_id'], ['core.cuenta.id'], name=op.f('fk_entrada_diccionario_cuenta_id_cuenta'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_entrada_diccionario')),
    sa.UniqueConstraint('cuenta_id', 'tipo', 'clave', name='entrada_diccionario_unique'),
    schema='core'
    )
    # ### end Alembic commands ###

    conn = op.get_bind()
    cuenta_ids = [fila[0] for fila in conn.execute(sa.text('SELECT id FROM core.cuenta')).fetchall()]
    for cuenta_id in cuenta_ids:
        _sembrar(conn, cuenta_id, tipo='pais', entradas=PAISES)
        _sembrar(conn, cuenta_id, tipo='forma_pago', entradas=FORMAS_PAGO)


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
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('entrada_diccionario', schema='core')
    # ### end Alembic commands ###
