"""Política de redondeo.

Convención Presto/FIEBDC: el precio se redondea **en cada nivel** de la
descomposición, no solo al presentar. Es lo que hace que un presupuesto cuadre
al céntimo contra Presto o Arquímedes; arrastrar todos los decimales y
redondear al final da diferencias de céntimos que los técnicos detectan y no
saben justificar.

Se redondea con ROUND_HALF_UP (el redondeo comercial), no con el banquero que
Python trae por defecto en `round()`.
"""

from decimal import ROUND_HALF_UP, Decimal

# Precios y importes: dos decimales.
PRECISION_PRECIO = Decimal("0.01")
# Rendimientos: seis, para que un 1/3 no se deforme al encadenar.
PRECISION_RENDIMIENTO = Decimal("0.000001")
# Mediciones: tres.
PRECISION_MEDICION = Decimal("0.001")
# Precios de suministro (tarifas de proveedor): cuatro.
PRECISION_SUMINISTRO = Decimal("0.0001")


def redondear_precio(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISION_PRECIO, rounding=ROUND_HALF_UP)


def redondear_rendimiento(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISION_RENDIMIENTO, rounding=ROUND_HALF_UP)


def redondear_medicion(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISION_MEDICION, rounding=ROUND_HALF_UP)


def redondear_suministro(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISION_SUMINISTRO, rounding=ROUND_HALF_UP)
