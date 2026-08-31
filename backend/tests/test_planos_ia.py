"""Lectura de un plano con IA.

Lo que se prueba aquí no es que el modelo acierte —eso no es determinista—
sino las dos cosas que sí lo son y que pueden hacer daño: la cuenta de la
escala de papel, que tiene que ser exacta, y el filtro de lo que devuelve el
modelo, que es lo único que impide que una lectura mala calibre un plano
entero con un número inventado.
"""

from decimal import Decimal

import pytest

from app.modules.planos.ia import LecturaFallida, _parsear, escala_de_papel

# ── La cuenta del papel ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("denominador", "metros_por_punto"),
    [
        (1, Decimal("25.4") / 72 / 1000),
        (50, Decimal("25.4") * 50 / 72 / 1000),
        (100, Decimal("25.4") * 100 / 72 / 1000),
    ],
)
def test_escala_de_papel(denominador, metros_por_punto):
    assert escala_de_papel(denominador) == metros_por_punto


def test_una_pared_de_diez_metros_a_1_50_ocupa_200_mm_de_papel():
    """La comprobación que de verdad importa: a escala 1:50, diez metros de
    obra tienen que caber en 200 mm de papel. Si esta cuenta está mal, todas
    las mediciones del plano lo están."""
    escala = escala_de_papel(50)
    puntos = Decimal(10) / escala          # cuántos puntos son 10 m
    mm_papel = puntos * Decimal("25.4") / 72
    assert abs(mm_papel - Decimal(200)) < Decimal("0.0001")


def test_a_1_100_lo_mismo_ocupa_la_mitad():
    assert escala_de_papel(100) == escala_de_papel(50) * 2


def test_una_escala_de_cero_no_calibra():
    with pytest.raises(LecturaFallida):
        escala_de_papel(0)


# ── El filtro de lo que devuelve el modelo ──────────────────────────────


def test_lee_la_escala_y_las_cotas():
    lectura = _parsear(
        '{"escala_denominador": 50, "escala_texto": "E 1:50", '
        '"cotas": [{"texto": "10,00", "metros": 10, "donde": "fachada sur"}], '
        '"resumen": "Planta baja", "avisos": []}'
    )
    assert lectura.escala_impresa == 50
    assert lectura.escala_texto == "E 1:50"
    assert lectura.cotas[0].metros == Decimal(10)
    assert lectura.cotas[0].donde == "fachada sur"


def test_una_escala_que_no_se_usa_se_rechaza_y_se_dice():
    """«1:57» es un «1:50» mal leído. Aceptarlo calibraría el plano entero con
    un número inventado, y un 14 % de error no se ve: se cobra."""
    lectura = _parsear('{"escala_denominador": 57, "cotas": [], "avisos": []}')
    assert lectura.escala_impresa is None
    assert any("1:57" in a for a in lectura.avisos)


def test_sin_escala_no_se_supone_ninguna():
    lectura = _parsear('{"escala_denominador": null, "cotas": [], "avisos": []}')
    assert lectura.escala_impresa is None


@pytest.mark.parametrize("metros", [0, -3, 5000, 0.001])
def test_las_cotas_absurdas_se_descartan(metros):
    """Una cota de cero, negativa o de cinco kilómetros no es una cota de un
    plano de obra: es una lectura mala."""
    lectura = _parsear(
        f'{{"escala_denominador": null, "cotas": [{{"texto": "x", "metros": {metros}}}], '
        '"avisos": []}'
    )
    assert lectura.cotas == []


def test_una_cota_sin_numero_no_tumba_la_lectura():
    lectura = _parsear(
        '{"escala_denominador": 50, "cotas": ['
        '{"texto": "ilegible", "metros": "no es un número"},'
        '{"texto": "3,20", "metros": 3.2}], "avisos": []}'
    )
    assert lectura.escala_impresa == 50
    assert len(lectura.cotas) == 1
    assert lectura.cotas[0].metros == Decimal("3.2")


def test_admite_la_respuesta_envuelta_en_un_bloque_de_codigo():
    """Los modelos devuelven el JSON entre ``` más a menudo de lo que
    prometen."""
    lectura = _parsear('```json\n{"escala_denominador": 100, "cotas": []}\n```')
    assert lectura.escala_impresa == 100


@pytest.mark.parametrize("texto", ["no soy json", "[1,2,3]", ""])
def test_una_respuesta_ilegible_falla_en_vez_de_devolver_vacio(texto):
    """Devolver una lectura vacía se leería como «el plano no dice nada», que
    es distinto de «no me he enterado»."""
    with pytest.raises(LecturaFallida):
        _parsear(texto)


def test_se_topan_las_cotas_y_los_avisos():
    muchas = ",".join(f'{{"texto":"{i}","metros":{i + 1}}}' for i in range(40))
    lectura = _parsear(
        f'{{"escala_denominador": 50, "cotas": [{muchas}], '
        f'"avisos": [{",".join(chr(34) + str(i) + chr(34) for i in range(20))}]}}'
    )
    assert len(lectura.cotas) <= 20
    assert len(lectura.avisos) <= 6
