from decimal import Decimal

import pytest

from app.modules.presupuestos.fiebdc.importador import (
    calcular_precios,
    detectar_ciclos,
    orden_topologico,
)
from app.modules.presupuestos.fiebdc.lector import detectar_codificacion, leer_registros
from app.modules.presupuestos.fiebdc.modelo import TipoConceptoBC3
from app.modules.presupuestos.fiebdc.parser import a_decimal, a_fecha, parsear

# Presupuesto mínimo pero completo: raíz, dos capítulos, un unitario con
# auxiliar, básicos, textos y mediciones.
BC3 = "\r\n".join(
    [
        "~V|Obra de prueba|FIEBDC-3/2016\\08/08/2026|Redactor|Rehabilitación|ANSI||",
        "~C|OBRA##||Rehabilitación de fachada|0|08082026|0|",
        "~C|01#||Albañilería|0||0|",
        "~C|02#||Seguridad y salud|0||0|",
        "~C|MO001|h|Oficial 1ª albañil|19.50|08082026|1|",
        "~C|MO002|h|Peón ordinario|17.20|08082026|1|",
        "~C|MT001|kg|Cemento CEM II/B-L 32,5 N|0.20|08082026|3|",
        "~C|MT002|m3|Arena de río 0/5 mm|12.00|08082026|3|",
        # Precios coherentes con su descomposición:
        #   AUX001 = 300x0,20 + 1,1x12,00 + 1,7x17,20 = 102,44
        #   U001   = 0,03x102,44 + 0,85x19,50 + 0,85x17,20 = 3,07 + 16,58 + 14,62
        "~C|AUX001|m3|Mortero de cemento M-5|102.44||0|",
        "~C|U001|m2|Fábrica de ladrillo perforado|34.27||0|",
        "~C|SS001|ud|Partida alzada de seguridad|1450.00||0|",
        "~T|U001|Fábrica de ladrillo perforado de medio pie de espesor.|",
        "~D|OBRA##|01#\\1\\1\\02#\\1\\1|",
        "~D|01#|U001\\1\\186.480|",
        "~D|02#|SS001\\1\\1|",
        "~D|AUX001|MT001\\1\\300\\MT002\\1\\1.1\\MO002\\1\\1.7|",
        "~D|U001|AUX001\\1\\0.03\\MO001\\1\\0.85\\MO002\\1\\0.85|",
        "~M|01#\\U001|1|186.480|"
        "\\Fachada principal\\1\\12.40\\\\9.60\\"
        "\\Fachada patio\\1\\8.15\\\\9.60\\"
        "\\A deducir huecos\\-6\\1.20\\\\1.50\\|",
        "",
    ]
)


@pytest.fixture
def archivo():
    return parsear(BC3.encode("cp1252"))


# --- Lector ---


def test_detecta_ansi_declarado():
    assert detectar_codificacion(BC3.encode("cp1252")) == "cp1252"


def test_detecta_utf8_declarado():
    texto = BC3.replace("|ANSI||", "|UTF-8||")
    assert detectar_codificacion(texto.encode("utf-8")) == "utf-8"


def test_sin_declaracion_supone_ansi():
    """Presto y Arquímedes emiten cp1252 cuando no declaran nada; suponer
    UTF-8 destrozaría todas las tildes."""
    assert detectar_codificacion(b"~C|A|ud|Hormigon|1|||") == "cp1252"


def test_las_tildes_sobreviven_al_viaje(archivo):
    assert archivo.conceptos["MO001"].resumen == "Oficial 1ª albañil"
    assert archivo.cabecera == "Rehabilitación"


def test_registro_partido_en_varias_lineas():
    """Un registro sigue hasta la siguiente línea que empiece por '~'."""
    texto = "~C|A|ud|Descripción\nque sigue abajo|10|||\n~C|B|ud|Otra|5|||"
    registros = list(leer_registros(texto))
    assert len(registros) == 2
    assert "que sigue abajo" in registros[0].campos[2]


def test_pedir_un_campo_que_no_viene_no_revienta():
    """Los BC3 reales omiten campos finales constantemente."""
    registros = list(leer_registros("~C|A|ud|Cosa|"))
    assert registros[0].campo(9) == ""
    assert registros[0].subcampos(9) == []


# --- Conversiones ---


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("12.50", "12.50"), ("12,50", "12.50"), ("", None), ("no", None), ("-6", "-6")],
)
def test_numeros(texto, esperado):
    resultado = a_decimal(texto)
    assert resultado == (Decimal(esperado) if esperado else None)


def test_fecha_en_los_dos_ordenes_que_circulan():
    assert a_fecha("08082026") == a_fecha("20260808")
    assert a_fecha("08082026").isoformat() == "2026-08-08"


def test_fecha_ilegible_no_rompe_la_importacion():
    assert a_fecha("99999999") is None
    assert a_fecha("") is None


# --- Clasificación por estructura ---


def test_raiz_y_capitulos_por_sufijo(archivo):
    assert archivo.conceptos["OBRA##"].tipo is TipoConceptoBC3.RAIZ
    assert archivo.conceptos["01#"].tipo is TipoConceptoBC3.CAPITULO


def test_basico_es_el_que_no_se_descompone(archivo):
    for codigo in ("MO001", "MO002", "MT001", "MT002"):
        assert archivo.conceptos[codigo].tipo is TipoConceptoBC3.BASICO


def test_auxiliar_es_el_descompuesto_que_entra_en_otro_descompuesto(archivo):
    assert archivo.conceptos["AUX001"].tipo is TipoConceptoBC3.AUXILIAR


def test_unitario_es_el_que_cuelga_de_un_capitulo(archivo):
    assert archivo.conceptos["U001"].tipo is TipoConceptoBC3.UNITARIO
    assert archivo.conceptos["SS001"].tipo is TipoConceptoBC3.BASICO


def test_reconoce_que_es_un_presupuesto_y_no_un_banco(archivo):
    assert archivo.es_presupuesto


def test_un_banco_de_precios_no_se_confunde_con_una_obra():
    banco = "\r\n".join(
        [
            "~V|Banco|FIEBDC-3/2016\\08/08/2026|Redactor|Precios|ANSI||",
            "~C|MO001|h|Oficial|19.50|||",
            "~C|MT001|kg|Cemento|0.20|||",
        ]
    )
    archivo = parsear(banco.encode("cp1252"))
    assert not archivo.es_presupuesto
    assert archivo.raiz is None


# --- Descomposición y mediciones ---


def test_descomposicion_en_tripletes(archivo):
    lineas = archivo.descomposiciones["AUX001"]
    assert [l.hijo for l in lineas] == ["MT001", "MT002", "MO002"]
    assert lineas[0].rendimiento == Decimal("300")
    assert lineas[0].factor == Decimal("1")


def test_lineas_de_medicion_en_grupos_de_seis(archivo):
    medicion = archivo.mediciones[0]
    assert (medicion.padre, medicion.hijo) == ("01#", "U001")
    assert len(medicion.lineas) == 3
    assert medicion.lineas[0].comentario == "Fachada principal"
    assert medicion.lineas[0].longitud == Decimal("12.40")
    assert medicion.lineas[0].anchura is None
    assert medicion.lineas[2].uds == Decimal("-6")


def test_el_texto_largo_se_asocia_a_su_concepto(archivo):
    assert archivo.conceptos["U001"].texto.startswith("Fábrica de ladrillo perforado de medio")


# --- Cálculo ---


def test_orden_topologico_pone_los_hijos_antes(archivo):
    orden = orden_topologico(archivo)
    assert orden.index("MT001") < orden.index("AUX001") < orden.index("U001")


def test_precios_calculados_coinciden_con_los_del_fichero(archivo):
    """La prueba de fuego: nuestro redondeo tiene que dar lo mismo que el
    programa que generó el BC3."""
    precios, discrepancias = calcular_precios(archivo)
    assert precios["AUX001"] == Decimal("102.44")
    # 0,85 x 19,50 = 16,575, que con redondeo comercial sube a 16,58.
    assert precios["U001"] == Decimal("34.27")
    assert discrepancias == []


def test_se_delata_la_discrepancia_de_precio():
    """Si el fichero declara un precio que no cuadra con su descomposición, hay
    que decirlo en vez de tragarlo en silencio."""
    texto = "\r\n".join(
        [
            "~V|X|FIEBDC-3/2016\\08/08/2026|R|X|ANSI||",
            "~C|B1|ud|Básico|10.00|||",
            "~C|U1|ud|Unitario|999.00|||",
            "~D|U1|B1\\1\\2|",
        ]
    )
    archivo = parsear(texto.encode("cp1252"))
    precios, discrepancias = calcular_precios(archivo)
    assert precios["U1"] == Decimal("20.00")
    assert discrepancias == [("U1", Decimal("20.00"), Decimal("999.00"))]


def test_se_detectan_los_ciclos_antes_de_escribir_nada():
    texto = "\r\n".join(
        [
            "~V|X|FIEBDC-3/2016\\08/08/2026|R|X|ANSI||",
            "~C|A|ud|A|1|||",
            "~C|B|ud|B|1|||",
            "~D|A|B\\1\\1|",
            "~D|B|A\\1\\1|",
        ]
    )
    archivo = parsear(texto.encode("cp1252"))
    assert detectar_ciclos(archivo)


def test_un_fichero_sano_no_tiene_ciclos(archivo):
    assert detectar_ciclos(archivo) == []


# --- Tolerancia ---


def test_los_registros_desconocidos_se_anotan_pero_no_estorban():
    texto = "\r\n".join(
        [
            "~V|X|FIEBDC-3/2016\\08/08/2026|R|X|ANSI||",
            "~Z|algo raro que no entendemos|",
            "~C|B1|ud|Básico|10.00|||",
        ]
    )
    archivo = parsear(texto.encode("cp1252"))
    assert "B1" in archivo.conceptos
    assert any(i.registro == "~Z" for i in archivo.incidencias)


def test_basura_antes_del_primer_registro_se_ignora():
    texto = "Generado por un programa cualquiera\r\n~C|B1|ud|Básico|10.00|||"
    archivo = parsear(texto.encode("cp1252"))
    assert "B1" in archivo.conceptos
