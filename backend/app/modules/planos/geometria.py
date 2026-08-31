"""Las cuentas de medir sobre un plano.

Está aparte del servicio porque es la parte que se puede probar sin base de
datos ni ficheros, y es la que hay que blindar: un error aquí no da un error,
da una medición equivocada que nadie revisa porque «lo ha medido el programa».

Todo en `Decimal`. Con `float`, sumar cien tramos de fachada arrastra un error
que acaba viéndose en la certificación, y eso es dinero.
"""

from decimal import Decimal, InvalidOperation

#: Metros. Por debajo de esto, un trazo es un clic doble o un temblor de mano,
#: no una medida — y aceptarlo mete ruido en los totales.
MINIMO_SIGNIFICATIVO = Decimal("0.001")


class GeometriaInvalida(Exception):
    """La forma no sirve para lo que se pretende medir."""


def _punto(bruto: object) -> tuple[Decimal, Decimal]:
    if not isinstance(bruto, dict):
        raise GeometriaInvalida("Cada punto tiene que ser un objeto con x e y")
    try:
        return Decimal(str(bruto["x"])), Decimal(str(bruto["y"]))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise GeometriaInvalida("Un punto sin x/y numéricas") from exc


def puntos(geometria: list) -> list[tuple[Decimal, Decimal]]:
    if not isinstance(geometria, list):
        raise GeometriaInvalida("La geometría es una lista de puntos")
    return [_punto(p) for p in geometria]


def _raiz(valor: Decimal) -> Decimal:
    """Raíz cuadrada sin pasar por `float`.

    `Decimal.sqrt()` respeta el contexto decimal, así que la longitud de un
    tramo no pierde precisión por convertir a coma flotante y volver.
    """
    if valor <= 0:
        return Decimal(0)
    return valor.sqrt()


def longitud(geometria: list, metros_por_unidad: Decimal) -> Decimal:
    """Longitud de una polilínea, en metros."""
    ps = puntos(geometria)
    if len(ps) < 2:
        raise GeometriaInvalida("Una longitud necesita al menos dos puntos")
    total = Decimal(0)
    for (x1, y1), (x2, y2) in zip(ps, ps[1:], strict=False):
        total += _raiz((x2 - x1) ** 2 + (y2 - y1) ** 2)
    return total * metros_por_unidad


def area(geometria: list, metros_por_unidad: Decimal) -> Decimal:
    """Área de un polígono por la fórmula del zapatero, en metros cuadrados.

    Se cierra solo: quien dibuja no tiene por qué acertar a volver al primer
    punto con el ratón, y exigirlo daría áreas mal por un píxel.

    El valor absoluto no es un descuido: el signo del zapatero dice si el
    polígono se recorrió en un sentido o en el otro, y eso no cambia cuánto
    mide el suelo.
    """
    ps = puntos(geometria)
    if len(ps) < 3:
        raise GeometriaInvalida("Un área necesita al menos tres puntos")
    doble = Decimal(0)
    for (x1, y1), (x2, y2) in zip(ps, ps[1:] + ps[:1], strict=False):
        doble += x1 * y2 - x2 * y1
    return abs(doble) / 2 * (metros_por_unidad**2)


def conteo(geometria: list) -> Decimal:
    """Cuántos puntos hay. No depende de la escala: contar arquetas sale igual
    esté el plano calibrado o no."""
    return Decimal(len(puntos(geometria)))


def escala_desde_cota(
    a: dict, b: dict, distancia_real_m: Decimal
) -> Decimal:
    """Metros por unidad de hoja, a partir de dos puntos y la cota que los
    separa de verdad.

    Es como se calibra un plano escaneado: se pincha una cota conocida y se
    teclea cuánto mide. Todo lo demás sale de aquí, así que se comprueba en
    serio antes de aceptarla — una escala mal puesta no da un error, da un
    presupuesto entero equivocado.
    """
    if distancia_real_m <= 0:
        raise GeometriaInvalida("La distancia real tiene que ser mayor que cero")
    (x1, y1), (x2, y2) = _punto(a), _punto(b)
    separacion = _raiz((x2 - x1) ** 2 + (y2 - y1) ** 2)
    if separacion <= 0:
        raise GeometriaInvalida("Los dos puntos de la cota son el mismo")
    return distancia_real_m / separacion
