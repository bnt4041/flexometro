import uuid
from decimal import Decimal

import pytest

from app.core.redondeo import redondear_precio, redondear_rendimiento
from app.modules.presupuestos.models import (
    Concepto,
    Descomposicion,
    TipoConcepto,
)
from app.modules.presupuestos.service import clase_de, coste_directo_de, lineas_de


def concepto(tipo: TipoConcepto, codigo: str, precio: str = "0.00", **extra) -> Concepto:
    # Los identificadores se asignan a mano: estos tests no tocan la base de
    # datos, y sin flush las claves seguirían a None.
    return Concepto(
        id=uuid.uuid4(),
        codigo=codigo,
        tipo=tipo,
        resumen=codigo,
        unidad="ud",
        precio=Decimal(precio),
        **extra,
    )


def linea(padre: Concepto, hijo: Concepto, rendimiento: str, factor: str = "1"):
    # Asignar `padre=` ya encola la línea en `padre.lineas` por el
    # back_populates; añadirla otra vez a mano la duplicaría.
    return Descomposicion(
        id=uuid.uuid4(),
        padre=padre,
        hijo=hijo,
        padre_id=padre.id,
        hijo_id=hijo.id,
        rendimiento=Decimal(rendimiento),
        factor=Decimal(factor),
        orden=len(padre.lineas),
    )


# --- Redondeo ---


def test_redondeo_comercial_no_bancario():
    """Python redondea a par por defecto; la convención Presto es al alza."""
    assert redondear_precio(Decimal("16.575")) == Decimal("16.58")
    assert redondear_precio(Decimal("2.345")) == Decimal("2.35")
    assert redondear_precio(Decimal("0.005")) == Decimal("0.01")


def test_rendimiento_conserva_seis_decimales():
    assert redondear_rendimiento(Decimal("1") / Decimal("3")) == Decimal("0.333333")


# --- Importes de línea ---


def test_importe_de_linea_se_redondea_antes_de_sumar():
    """Es lo que hace que el descompuesto impreso cuadre columna a columna."""
    padre = concepto(TipoConcepto.UNITARIO, "U1")
    linea(padre, concepto(TipoConcepto.BASICO, "B1", "19.50"), "0.85")
    linea(padre, concepto(TipoConcepto.BASICO, "B2", "17.20"), "0.85")

    importes = [l.importe for l in lineas_de(padre)]
    assert importes == [Decimal("16.58"), Decimal("14.62")]
    assert coste_directo_de(lineas_de(padre)) == Decimal("31.20")


def test_el_factor_multiplica_al_rendimiento():
    """FIEBDC-3 separa FACTOR de RENDIMIENTO; el importe usa los dos."""
    padre = concepto(TipoConcepto.AUXILIAR, "A1")
    linea(padre, concepto(TipoConcepto.BASICO, "B1", "10.00"), "2", factor="1.5")
    assert lineas_de(padre)[0].importe == Decimal("30.00")


def test_coste_directo_de_descompuesto_vacio_es_cero():
    padre = concepto(TipoConcepto.UNITARIO, "U1")
    assert coste_directo_de(lineas_de(padre)) == Decimal("0.00")


# --- Clasificación del unitario (Ramírez de Arellano) ---


def test_unitario_solo_con_basicos_es_simple():
    u = concepto(TipoConcepto.UNITARIO, "U1")
    linea(u, concepto(TipoConcepto.BASICO, "B1", "1.00"), "1")
    linea(u, concepto(TipoConcepto.BASICO, "B2", "2.00"), "1")
    assert clase_de(u) == "simple"


def test_unitario_con_auxiliar_es_complejo():
    u = concepto(TipoConcepto.UNITARIO, "U1")
    linea(u, concepto(TipoConcepto.BASICO, "B1", "1.00"), "1")
    linea(u, concepto(TipoConcepto.AUXILIAR, "A1", "75.68"), "0.03")
    assert clase_de(u) == "complejo"


def test_unitario_que_agrupa_unitarios_es_funcional():
    u = concepto(TipoConcepto.UNITARIO, "U1")
    linea(u, concepto(TipoConcepto.AUXILIAR, "A1", "10.00"), "1")
    linea(u, concepto(TipoConcepto.UNITARIO, "U2", "34.47"), "1")
    assert clase_de(u) == "funcional"


@pytest.mark.parametrize("tipo", [TipoConcepto.BASICO, TipoConcepto.AUXILIAR])
def test_la_clase_solo_aplica_a_unitarios(tipo):
    c = concepto(tipo, "X1")
    linea(c, concepto(TipoConcepto.BASICO, "B1", "1.00"), "1")
    assert clase_de(c) is None


def test_unitario_sin_descomponer_no_tiene_clase():
    assert clase_de(concepto(TipoConcepto.UNITARIO, "U1", "50.00")) is None
