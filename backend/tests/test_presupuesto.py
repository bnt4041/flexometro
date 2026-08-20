from decimal import Decimal

import pytest

from app.core.enums import TipoIVA
from app.modules.presupuestos.models_presupuesto import (
    ESTADOS_BLOQUEADOS,
    EstadoPresupuesto,
    MetodoCalculo,
    Presupuesto,
)
from app.modules.presupuestos.presupuesto_calculo import (
    PorcentajeImposible,
    Totales,
    parcial_de,
    resolver_porcentaje_objetivo,
    venta_unitaria,
)


def d(valor: str | None) -> Decimal | None:
    return None if valor is None else Decimal(valor)


# --- Parcial de una línea de medición ---


@pytest.mark.parametrize(
    ("uds", "longitud", "anchura", "altura", "esperado"),
    [
        # Las dimensiones no informadas valen 1, no 0.
        ("5", None, None, None, "5.000"),
        ("1", "12.40", None, "9.60", "119.040"),
        ("2", "3.50", "0.40", "0.30", "0.840"),
        (None, "10", None, None, "10.000"),
        # Un cero explícito sí anula: es lo que se espera al teclearlo.
        ("0", "12.40", None, "9.60", "0.000"),
        # Negativo para deducir huecos, práctica corriente en medición.
        ("-6", "1.20", "1.50", None, "-10.800"),
    ],
)
def test_parcial(uds, longitud, anchura, altura, esperado):
    assert parcial_de(d(uds), d(longitud), d(anchura), d(altura)) == Decimal(esperado)


def test_linea_completamente_vacia_mide_cero():
    assert parcial_de(None, None, None, None) == Decimal("0.000")


def test_parcial_se_redondea_a_tres_decimales():
    assert parcial_de(d("1"), d("1.0005"), None, None) == Decimal("1.001")


# --- Encadenado PEM -> PEC ---


def presupuesto(**extra) -> Presupuesto:
    valores = {
        "gastos_generales": Decimal("13.00"),
        "beneficio_industrial": Decimal("6.00"),
        "tipo_iva": TipoIVA.GENERAL,
        "inversion_sujeto_pasivo": False,
    }
    valores.update(extra)
    return Presupuesto(codigo="PRE00001", nombre="Prueba", **valores)


def test_encadenado_completo():
    t = Totales(presupuesto(), Decimal("8291.31"))
    assert t.pem == Decimal("8291.31")
    assert t.gastos_generales == Decimal("1077.87")
    assert t.beneficio_industrial == Decimal("497.48")
    assert t.pec_sin_iva == Decimal("9866.66")
    assert t.iva == Decimal("2072.00")
    assert t.total == Decimal("11938.66")


def test_gg_y_bi_se_calculan_sobre_el_pem_no_en_cascada():
    """El 6 % de beneficio industrial va sobre el PEM, no sobre PEM + gastos
    generales: encadenarlos inflaría el presupuesto."""
    t = Totales(presupuesto(), Decimal("1000.00"))
    assert t.gastos_generales == Decimal("130.00")
    assert t.beneficio_industrial == Decimal("60.00")
    assert t.pec_sin_iva == Decimal("1190.00")


def test_inversion_del_sujeto_pasivo_deja_el_iva_a_cero():
    """En obra subcontratada la factura va sin IVA (art. 84.Uno.2.º f LIVA)."""
    t = Totales(presupuesto(inversion_sujeto_pasivo=True), Decimal("1000.00"))
    assert t.porcentaje_iva == Decimal("0")
    assert t.iva == Decimal("0.00")
    assert t.total == t.pec_sin_iva == Decimal("1190.00")


def test_iva_reducido():
    t = Totales(presupuesto(tipo_iva=TipoIVA.REDUCIDO), Decimal("1000.00"))
    assert t.porcentaje_iva == Decimal("10")
    assert t.iva == Decimal("119.00")


def test_presupuesto_vacio_no_rompe():
    t = Totales(presupuesto(), Decimal("0.00"))
    assert t.total == Decimal("0.00")


def test_sin_gastos_generales_ni_beneficio():
    t = Totales(
        presupuesto(gastos_generales=Decimal("0"), beneficio_industrial=Decimal("0")),
        Decimal("1000.00"),
    )
    assert t.pec_sin_iva == Decimal("1000.00")


# --- Estados ---


def test_solo_el_borrador_sigue_al_cuadro_de_precios():
    assert EstadoPresupuesto.BORRADOR not in ESTADOS_BLOQUEADOS
    for estado in (
        EstadoPresupuesto.EMITIDO,
        EstadoPresupuesto.APROBADO,
        EstadoPresupuesto.RECHAZADO,
        EstadoPresupuesto.CANCELADO,
    ):
        assert estado in ESTADOS_BLOQUEADOS


# --- Reajuste: qué porcentaje despeja cada método (Fase 38) ---


def test_reajuste_incremento_sobre_coste_despeja_el_recargo():
    porcentaje, gg, bi = resolver_porcentaje_objetivo(
        MetodoCalculo.INCREMENTO_SOBRE_COSTE,
        Decimal("13.00"),
        Decimal("6.00"),
        Decimal("1000.00"),
        Decimal("1200.00"),
    )
    assert porcentaje == Decimal("20.00")
    # Ajenos a este método: se devuelven sin tocar.
    assert (gg, bi) == (Decimal("13.00"), Decimal("6.00"))
    assert venta_unitaria(Decimal("1000.00"), MetodoCalculo.INCREMENTO_SOBRE_COSTE, porcentaje) == Decimal(
        "1200.00"
    )


def test_reajuste_beneficio_final_convierte_el_recargo_a_margen_sobre_la_venta():
    # coste 800 -> venta 1000 es un recargo del 25 %, pero un margen del 20 %
    # sobre la venta (200 de beneficio son el 20 % de 1000, no del coste).
    porcentaje, _, _ = resolver_porcentaje_objetivo(
        MetodoCalculo.BENEFICIO_FINAL,
        Decimal("13.00"),
        Decimal("6.00"),
        Decimal("800.00"),
        Decimal("1000.00"),
    )
    assert porcentaje == Decimal("20.00")
    assert venta_unitaria(Decimal("800.00"), MetodoCalculo.BENEFICIO_FINAL, porcentaje) == Decimal("1000.00")


def test_reajuste_clasico_reparte_el_recargo_a_prorrata_de_como_estaba():
    # GG=13, BI=6 (proporción 13:6). Doblar el recargo combinado (19 -> 38)
    # dobla igual cada uno de los dos, conservando la proporción.
    porcentaje, gg, bi = resolver_porcentaje_objetivo(
        MetodoCalculo.CLASICO,
        Decimal("13.00"),
        Decimal("6.00"),
        Decimal("1000.00"),
        Decimal("1380.00"),
    )
    assert porcentaje == Decimal("38.00")
    assert gg == Decimal("26.00")
    assert bi == Decimal("12.00")


def test_reajuste_clasico_sin_referencia_previa_va_todo_a_gastos_generales():
    porcentaje, gg, bi = resolver_porcentaje_objetivo(
        MetodoCalculo.CLASICO,
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("1000.00"),
        Decimal("1100.00"),
    )
    assert porcentaje == Decimal("10.00")
    assert gg == Decimal("10.00")
    assert bi == Decimal("0.00")


def test_reajuste_admite_vender_por_debajo_de_coste():
    """No se fuerza a 0: si el objetivo pide menos que el coste, el
    porcentaje sale negativo en vez de negarse a acercarse."""
    porcentaje, _, _ = resolver_porcentaje_objetivo(
        MetodoCalculo.INCREMENTO_SOBRE_COSTE,
        Decimal("13.00"),
        Decimal("6.00"),
        Decimal("1000.00"),
        Decimal("900.00"),
    )
    assert porcentaje == Decimal("-10.00")


def test_reajuste_rechaza_sin_coste_que_repartir():
    with pytest.raises(PorcentajeImposible):
        resolver_porcentaje_objetivo(
            MetodoCalculo.INCREMENTO_SOBRE_COSTE,
            Decimal("13.00"),
            Decimal("6.00"),
            Decimal("0.00"),
            Decimal("100.00"),
        )


def test_reajuste_beneficio_final_rechaza_vender_muy_por_debajo_del_coste():
    # objetivo_libre en 0 hace que el recargo sea exactamente -100 %: el
    # margen sobre la venta se dispara a infinito, no tiene solución.
    with pytest.raises(PorcentajeImposible):
        resolver_porcentaje_objetivo(
            MetodoCalculo.BENEFICIO_FINAL,
            Decimal("13.00"),
            Decimal("6.00"),
            Decimal("1000.00"),
            Decimal("0.00"),
        )


def test_reajuste_beneficio_final_rechaza_un_margen_del_100_por_ciento():
    # Un objetivo disparatadamente por encima del coste empuja el margen
    # (asintótico al 100 %) a redondear justo a 100,00.
    with pytest.raises(PorcentajeImposible):
        resolver_porcentaje_objetivo(
            MetodoCalculo.BENEFICIO_FINAL,
            Decimal("13.00"),
            Decimal("6.00"),
            Decimal("1.00"),
            Decimal("20001.00"),
        )


def test_reajuste_rechaza_un_objetivo_que_desbordaria_el_porcentaje():
    """Reproduce un fallo real: coste 124,03 € y un objetivo de 3750 € piden
    un recargo de casi el 2924 %, que no cabe en la columna `Numeric(5,2)`
    (antes reventaba con un 500 al intentar guardarlo)."""
    with pytest.raises(PorcentajeImposible):
        resolver_porcentaje_objetivo(
            MetodoCalculo.INCREMENTO_SOBRE_COSTE,
            Decimal("13.00"),
            Decimal("6.00"),
            Decimal("124.03"),
            Decimal("3750.00"),
        )
    with pytest.raises(PorcentajeImposible):
        resolver_porcentaje_objetivo(
            MetodoCalculo.CLASICO,
            Decimal("13.00"),
            Decimal("6.00"),
            Decimal("124.03"),
            Decimal("3750.00"),
        )


def test_reajuste_beneficio_final_admite_un_objetivo_muy_alto():
    """A diferencia de los otros dos, su porcentaje (el margen sobre la
    venta) nunca puede llegar a 1000: el mismo objetivo desproporcionado no
    tiene por qué rechazarse con este método."""
    porcentaje, _, _ = resolver_porcentaje_objetivo(
        MetodoCalculo.BENEFICIO_FINAL,
        Decimal("13.00"),
        Decimal("6.00"),
        Decimal("124.03"),
        Decimal("3750.00"),
    )
    assert Decimal("0") < porcentaje < Decimal("100")
