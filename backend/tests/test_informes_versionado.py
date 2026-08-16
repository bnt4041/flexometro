from decimal import Decimal

import pytest

from app.modules.presupuestos.informes import DOCUMENTOS, _formato_es
from app.modules.presupuestos.models_presupuesto import Presupuesto
from app.modules.presupuestos.versionado import CAMPOS_COPIABLES, CambioPartida


# --- Formato numérico español ---


@pytest.mark.parametrize(
    ("valor", "decimales", "esperado"),
    [
        ("1234.5", 2, "1.234,50"),
        ("1234567.89", 2, "1.234.567,89"),
        ("999.999", 2, "1.000,00"),
        ("0", 2, "0,00"),
        ("186.48", 3, "186,480"),
        ("21", 0, "21"),
        ("-10.8", 3, "-10,800"),
        ("-1234.5", 2, "-1.234,50"),
    ],
)
def test_formato_espanol(valor, decimales, esperado):
    assert _formato_es(Decimal(valor), decimales) == esperado


def test_valor_nulo_no_imprime_nada():
    assert _formato_es(None, 2) == ""


def test_millares_en_el_limite_de_los_grupos():
    assert _formato_es(Decimal("999"), 2) == "999,00"
    assert _formato_es(Decimal("1000"), 2) == "1.000,00"


# --- Documentos ---


def test_los_tres_documentos_tienen_plantilla_y_titulo():
    assert set(DOCUMENTOS) == {"presupuesto", "mediciones", "descompuestos"}
    for plantilla, titulo in DOCUMENTOS.values():
        assert plantilla.endswith(".html")
        assert titulo


# --- Copia profunda ---


def test_los_campos_copiables_existen_en_el_modelo():
    """Guarda contra una errata en la lista: un campo mal escrito reventaría
    solo al duplicar un presupuesto, que no es cuando quieres enterarte."""
    columnas = set(Presupuesto.__mapper__.attrs.keys())
    for campo in CAMPOS_COPIABLES:
        assert campo in columnas, f"'{campo}' no es un atributo de Presupuesto"


def test_la_copia_no_arrastra_estado_ni_version():
    """El estado, la versión y el cerrojo los decide quien copia, no el
    origen: una versión nueva nace en borrador y con los precios sueltos."""
    for campo in ("estado", "version", "precios_bloqueados", "raiz_id", "es_plantilla", "codigo"):
        assert campo not in CAMPOS_COPIABLES


# --- Comparación ---


def test_delta_de_un_cambio_de_importe():
    cambio = CambioPartida(
        clave="01/U00001",
        codigo="U00001",
        resumen="Fábrica de ladrillo",
        unidad="m2",
        importe_a=Decimal("7103.02"),
        importe_b=Decimal("8053.75"),
    )
    assert cambio.delta == Decimal("950.73")


def test_delta_negativo_al_reducir():
    cambio = CambioPartida(
        clave="02/SS.01",
        codigo="SS.01",
        resumen="Partida alzada",
        unidad="ud",
        importe_a=Decimal("1450.00"),
        importe_b=Decimal("0.00"),
    )
    assert cambio.delta == Decimal("-1450.00")


def test_alta_parte_de_cero():
    alta = CambioPartida(
        clave="02/SS.02", codigo="SS.02", resumen="Vallado", unidad="m",
        importe_b=Decimal("777.00"),
    )
    assert alta.importe_a == Decimal("0.00")
    assert alta.delta == Decimal("777.00")
