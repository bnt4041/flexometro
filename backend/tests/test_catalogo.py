from decimal import Decimal

import pytest

from app.core.enums import TIPO_IVA_PORCENTAJE, TipoIVA
from app.modules.catalogo.models import PrecioSuministro


def suministro(precio: str, descuento: str) -> PrecioSuministro:
    return PrecioSuministro(precio=Decimal(precio), descuento=Decimal(descuento))


def test_precio_neto_aplica_el_descuento_de_tarifa():
    assert suministro("0.1265", "12.50").precio_neto == Decimal("0.1107")


def test_precio_neto_sin_descuento_conserva_el_precio():
    assert suministro("14.9000", "0").precio_neto == Decimal("14.9000")


def test_precio_neto_conserva_cuatro_decimales():
    """El redondeo a dos de la convención Presto empieza en el precio básico,
    no aquí: truncar antes metería error en toda la cadena."""
    neto = suministro("0.0345", "3.00").precio_neto
    assert neto == Decimal("0.0335")
    assert neto.as_tuple().exponent == -4


def test_descuento_total_deja_precio_cero():
    assert suministro("25.0000", "100").precio_neto == Decimal("0.0000")


@pytest.mark.parametrize(
    ("tipo", "porcentaje"),
    [
        (TipoIVA.GENERAL, 21),
        (TipoIVA.REDUCIDO, 10),
        (TipoIVA.SUPERREDUCIDO, 4),
        (TipoIVA.EXENTO, 0),
    ],
)
def test_porcentajes_de_iva(tipo, porcentaje):
    assert TIPO_IVA_PORCENTAJE[tipo] == porcentaje
