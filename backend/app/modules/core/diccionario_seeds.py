"""Valores mínimos del diccionario para una cuenta nueva (Fase 40).

Mismas listas que sembraron las migraciones de las Fases 18/20/23
(`migrations/20260816_0819_diccionario_de_referencia.py`,
`20260816_0933_diccionarios_adicionales_estilo_dolibarr.py`,
`20260816_1025_iva_recargo_y_retencion_en_el_.py`) — aquellas solo
sembraron las cuentas que ya existían en el momento de migrar; esto cubre
las cuentas creadas después, en el momento en que se les crea su primera
organización (`core_service.crear_organizacion`).
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core.diccionario_models import EntradaDiccionario, TipoDiccionario

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

IVA: list[tuple[str, str, str]] = [
    ('general', 'General', '21'),
    ('reducido', 'Reducido', '10'),
    ('superreducido', 'Superreducido', '4'),
    ('exento', 'Exento', '0'),
]

RECARGO_EQUIVALENCIA: list[tuple[str, str, str]] = [
    ('general', 'Tipo general', '5.2'),
    ('reducido', 'Tipo reducido', '1.4'),
    ('superreducido', 'Tipo superreducido', '0.5'),
]

RETENCION: list[tuple[str, str, str]] = [
    ('general', 'General (profesionales)', '15'),
    ('nuevos_autonomos', 'Nuevos autónomos (2 primeros años)', '7'),
    ('modulos', 'Módulos', '1'),
    ('capital_mobiliario', 'Capital mobiliario', '19'),
    ('alquiler', 'Alquiler de inmuebles', '19'),
]

_SIN_VALOR: list[tuple[TipoDiccionario, list[tuple[str, str]]]] = [
    (TipoDiccionario.PAIS, PAISES),
    (TipoDiccionario.FORMA_PAGO, FORMAS_PAGO),
    (TipoDiccionario.PROVINCIA, PROVINCIAS),
    (TipoDiccionario.UNIDAD_MEDIDA, UNIDADES_MEDIDA),
    (TipoDiccionario.FORMA_JURIDICA, FORMAS_JURIDICAS),
    (TipoDiccionario.TRATAMIENTO, TRATAMIENTOS),
    (TipoDiccionario.CARGO, CARGOS),
]

_CON_VALOR: list[tuple[TipoDiccionario, list[tuple[str, str, str]]]] = [
    (TipoDiccionario.IVA, IVA),
    (TipoDiccionario.RECARGO_EQUIVALENCIA, RECARGO_EQUIVALENCIA),
    (TipoDiccionario.RETENCION, RETENCION),
]


async def sembrar_minimos(session: AsyncSession, cuenta_id: uuid.UUID) -> None:
    """Diccionario base para una cuenta nueva. Solo siembra si la cuenta
    todavía no tiene ninguna entrada — así una segunda organización de la
    misma cuenta no vuelve a intentarlo (chocaría con la clave única
    `cuenta_id, tipo, clave` sin aportar nada)."""
    ya_tiene = await session.scalar(
        select(func.count()).select_from(EntradaDiccionario).where(EntradaDiccionario.cuenta_id == cuenta_id)
    )
    if ya_tiene:
        return

    for tipo, entradas in _SIN_VALOR:
        for orden, (clave, etiqueta) in enumerate(entradas):
            session.add(
                EntradaDiccionario(
                    cuenta_id=cuenta_id, tipo=tipo, clave=clave, etiqueta=etiqueta, orden=orden
                )
            )
    for tipo, entradas in _CON_VALOR:
        for orden, (clave, etiqueta, valor) in enumerate(entradas):
            session.add(
                EntradaDiccionario(
                    cuenta_id=cuenta_id,
                    tipo=tipo,
                    clave=clave,
                    etiqueta=etiqueta,
                    valor=Decimal(valor),
                    orden=orden,
                )
            )
    await session.flush()
