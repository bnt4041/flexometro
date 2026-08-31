"""Las cuentas de medir sobre un plano.

Son la parte que hay que blindar de verdad: un fallo aquí no rompe nada
visiblemente, devuelve una medición equivocada que nadie revisa porque «la ha
medido el programa». Y de ahí sale una certificación.
"""

from decimal import Decimal

import pytest

from app.modules.planos.geometria import (
    GeometriaInvalida,
    area,
    conteo,
    escala_desde_cota,
    longitud,
)

# Una hoja donde una unidad son 10 cm: un tramo de 50 unidades mide 5 m.
DECIMETRO = Decimal("0.1")
UNO = Decimal(1)


def _p(x, y):
    return {"x": x, "y": y}


# ── Longitud ────────────────────────────────────────────────────────────


def test_tramo_recto():
    assert longitud([_p(0, 0), _p(50, 0)], DECIMETRO) == Decimal("5.0")


def test_pitagoras():
    """3-4-5, para que se vea que no está midiendo en bounding box."""
    assert longitud([_p(0, 0), _p(3, 4)], UNO) == Decimal(5)


def test_polilinea_suma_los_tramos():
    recorrido = [_p(0, 0), _p(10, 0), _p(10, 10), _p(0, 10)]
    assert longitud(recorrido, UNO) == Decimal(30)


def test_una_longitud_necesita_dos_puntos():
    with pytest.raises(GeometriaInvalida):
        longitud([_p(0, 0)], UNO)


# ── Área ────────────────────────────────────────────────────────────────


def test_rectangulo():
    cuadro = [_p(0, 0), _p(40, 0), _p(40, 20), _p(0, 20)]
    # 40 x 20 unidades = 4 m x 2 m = 8 m²
    assert area(cuadro, DECIMETRO) == Decimal(8)


def test_triangulo():
    assert area([_p(0, 0), _p(4, 0), _p(0, 3)], UNO) == Decimal(6)


def test_el_polinomo_se_cierra_solo():
    """Quien dibuja no tiene por qué acertar a volver al primer punto: repetirlo
    o no repetirlo tiene que dar lo mismo."""
    abierto = [_p(0, 0), _p(4, 0), _p(4, 3), _p(0, 3)]
    cerrado = abierto + [_p(0, 0)]
    assert area(abierto, UNO) == area(cerrado, UNO)


def test_el_sentido_del_recorrido_no_cambia_el_area():
    horario = [_p(0, 0), _p(0, 3), _p(4, 3), _p(4, 0)]
    antihorario = [_p(0, 0), _p(4, 0), _p(4, 3), _p(0, 3)]
    assert area(horario, UNO) == area(antihorario, UNO)


def test_forma_en_l():
    """Una planta en L: el zapatero tiene que dar el área real, no el
    rectángulo que la envuelve."""
    ele = [_p(0, 0), _p(6, 0), _p(6, 2), _p(2, 2), _p(2, 5), _p(0, 5)]
    assert area(ele, UNO) == Decimal(18)  # 6x2 + 2x3


def test_la_escala_entra_al_cuadrado():
    cuadro = [_p(0, 0), _p(10, 0), _p(10, 10), _p(0, 10)]
    assert area(cuadro, Decimal(2)) == Decimal(400)  # (10*2)²


def test_un_area_necesita_tres_puntos():
    with pytest.raises(GeometriaInvalida):
        area([_p(0, 0), _p(1, 1)], UNO)


# ── Conteo ──────────────────────────────────────────────────────────────


def test_conteo_no_depende_de_la_escala():
    puntos = [_p(1, 1), _p(2, 2), _p(3, 3)]
    assert conteo(puntos) == Decimal(3)


# ── Calibración ─────────────────────────────────────────────────────────


def test_calibrar_con_una_cota():
    """Una cota de 300 unidades que en realidad mide 6 m: cada unidad son 2 cm."""
    assert escala_desde_cota(_p(0, 0), _p(300, 0), Decimal(6)) == Decimal("0.02")


def test_calibrar_en_diagonal():
    assert escala_desde_cota(_p(0, 0), _p(30, 40), Decimal(10)) == Decimal("0.2")


def test_una_cota_de_cero_no_calibra():
    with pytest.raises(GeometriaInvalida):
        escala_desde_cota(_p(0, 0), _p(100, 0), Decimal(0))


def test_dos_puntos_iguales_no_calibran():
    with pytest.raises(GeometriaInvalida):
        escala_desde_cota(_p(5, 5), _p(5, 5), Decimal(3))


def test_calibrar_y_medir_cuadra():
    """La comprobación que de verdad importa: si calibro con una cota de 6 m y
    luego mido esa misma cota, tiene que salir 6 m."""
    a, b = _p(120, 40), _p(420, 440)
    escala = escala_desde_cota(a, b, Decimal(6))
    medido = longitud([a, b], escala)
    assert abs(medido - Decimal(6)) < Decimal("0.0001")


# ── Basura de entrada ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "geometria",
    [
        "no soy una lista",
        [{"x": 0}],
        [{"x": "hola", "y": 0}, {"x": 1, "y": 1}],
        [None, None],
    ],
)
def test_geometria_basura_no_pasa(geometria):
    with pytest.raises(GeometriaInvalida):
        longitud(geometria, UNO)
