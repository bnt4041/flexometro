from decimal import Decimal

from app.modules.compras.costes import _fila
from app.modules.compras.models import EstadoAlbaran
from app.modules.obras.models import EstadoObra


def test_desviacion_positiva_cuando_se_gasta_de_mas():
    fila = _fila(None, "01", "Albañilería", Decimal("1000.00"), Decimal("700.00"), Decimal("500.00"))
    assert fila.real_total == Decimal("1200.00")
    assert fila.desviacion == Decimal("200.00")
    assert fila.desviacion_pct == Decimal("20.0")


def test_desviacion_negativa_cuando_se_gasta_de_menos():
    fila = _fila(None, "02", "Seguridad y salud", Decimal("1450.00"), Decimal("340.00"), Decimal("0.00"))
    assert fila.real_total == Decimal("340.00")
    assert fila.desviacion == Decimal("-1110.00")
    # -1110/1450 = -76.55...% redondeado a una cifra decimal
    assert fila.desviacion_pct == Decimal("-76.6")


def test_capitulo_sin_presupuesto_pero_con_gasto_no_calcula_porcentaje():
    """Un capítulo padre que no lleva partidas propias pero recibe costes
    imputados por error (o a propósito) no puede dar un porcentaje sobre
    cero; se informa el importe y se deja el porcentaje a None."""
    fila = _fila(None, "01", "Albañilería", Decimal("0.00"), Decimal("250.00"), Decimal("486.00"))
    assert fila.real_total == Decimal("736.00")
    assert fila.desviacion == Decimal("736.00")
    assert fila.desviacion_pct is None


def test_capitulo_sin_presupuesto_ni_gasto():
    fila = _fila(None, "03", "Varios", Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
    assert fila.real_total == Decimal("0.00")
    assert fila.desviacion == Decimal("0.00")
    assert fila.desviacion_pct is None


def test_coste_exacto_al_presupuesto_no_desvia():
    fila = _fila(None, "04", "Exacto", Decimal("500.00"), Decimal("300.00"), Decimal("200.00"))
    assert fila.desviacion == Decimal("0.00")
    assert fila.desviacion_pct == Decimal("0.0")


def test_estados_de_obra():
    assert set(EstadoObra) == {
        EstadoObra.PLANIFICADA,
        EstadoObra.EN_EJECUCION,
        EstadoObra.PARALIZADA,
        EstadoObra.FINALIZADA,
        EstadoObra.CERRADA,
    }


def test_estados_de_albaran():
    assert set(EstadoAlbaran) == {
        EstadoAlbaran.BORRADOR,
        EstadoAlbaran.CONFORMADO,
        EstadoAlbaran.FACTURADO,
    }
