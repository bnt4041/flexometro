"""Lectura de DXF.

Se prueba contra ficheros generados aquí mismo con geometría conocida: es la
única forma de afirmar que medir sobre un DXF da el número exacto y no uno
parecido.
"""

import io
from decimal import Decimal

import ezdxf
import pytest

from app.modules.planos import dxf as lector
from app.modules.planos.geometria import area, longitud


def _fichero(doc) -> bytes:
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def _sala(unidades: int = 4):
    """Una sala de 10 x 5 m dibujada en milímetros, con una columna y una
    puerta metida como bloque — que es como vienen los planos de verdad."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = unidades
    doc.layers.add("MUROS")
    doc.layers.add("MOBILIARIO")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (10000, 0), (10000, 5000), (0, 5000)],
        close=True,
        dxfattribs={"layer": "MUROS"},
    )
    msp.add_circle((5000, 2500), 300, dxfattribs={"layer": "MUROS"})
    bloque = doc.blocks.new(name="PUERTA")
    # A propósito en la capa «0»: dentro de un bloque, eso significa «la capa
    # de quien me inserte».
    bloque.add_lwpolyline([(0, 0), (900, 0)])
    msp.add_blockref("PUERTA", (2000, 0), dxfattribs={"layer": "MOBILIARIO"})
    return doc


def test_lee_capas_y_geometria():
    d = lector.leer(_fichero(_sala()))
    assert set(d.capas) == {"MUROS", "MOBILIARIO"}
    assert len(d.trazos) >= 3


def test_las_unidades_salen_del_fichero():
    """Un DXF que declara milímetros nace calibrado: no hay que pinchar
    ninguna cota."""
    assert lector.leer(_fichero(_sala(unidades=4))).metros_por_unidad == Decimal("0.001")
    assert lector.leer(_fichero(_sala(unidades=6))).metros_por_unidad == Decimal("1")


def test_un_dxf_sin_unidades_no_se_inventa_la_escala():
    """`$INSUNITS = 0` es «sin unidades». Suponer milímetros sería acertar la
    mayoría de las veces y equivocarse en silencio el resto."""
    assert lector.leer(_fichero(_sala(unidades=0))).metros_por_unidad is None


def test_el_area_del_rectangulo_es_exacta():
    d = lector.leer(_fichero(_sala()))
    rect = max(
        (t for t in d.trazos if t.capa == "MUROS"),
        key=lambda t: max(p[0] for p in t.puntos),
    )
    forma = [{"x": x, "y": y} for x, y in rect.puntos]
    assert area(forma, d.metros_por_unidad) == Decimal(50)


def test_el_perimetro_tambien():
    d = lector.leer(_fichero(_sala()))
    rect = max(
        (t for t in d.trazos if t.capa == "MUROS"),
        key=lambda t: max(p[0] for p in t.puntos),
    )
    puntos = [*rect.puntos, rect.puntos[0]]
    forma = [{"x": x, "y": y} for x, y in puntos]
    assert longitud(forma, d.metros_por_unidad) == Decimal(30)


def test_los_bloques_se_explotan_en_la_capa_de_quien_los_inserta():
    """Regla de DXF: lo que está en la capa «0» dentro de un bloque hereda la
    capa del INSERT. Sin esto, puertas y mobiliario acaban todos en «0» y
    apagar su capa de verdad no los oculta."""
    d = lector.leer(_fichero(_sala()))
    assert [t for t in d.trazos if t.capa == "MOBILIARIO"]
    assert not [t for t in d.trazos if t.capa == "0"]


def test_el_dibujo_se_lleva_al_primer_cuadrante():
    """El origen de un DXF puede estar en cualquier parte (coordenadas UTM,
    por ejemplo). La hoja tiene que empezar en 0,0."""
    doc = ezdxf.new("R2010")
    doc.modelspace().add_lwpolyline(
        [(440000, 4470000), (440010, 4470000), (440010, 4470005)], close=True
    )
    d = lector.leer(_fichero(doc))
    assert all(x >= 0 and y >= 0 for t in d.trazos for x, y in t.puntos)
    assert 10 < d.ancho < 11


def test_la_y_se_invierte():
    """En DXF la Y crece hacia arriba y en pantalla hacia abajo. Sin
    invertirla el plano sale del revés, y con las cotas al revés nadie se da
    cuenta hasta haber medido mal."""
    doc = ezdxf.new("R2010")
    doc.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 100)], close=True)
    d = lector.leer(_fichero(doc))
    puntos = d.trazos[0].puntos
    # El (0,0) del DXF es la esquina de ABAJO, así que en la hoja tiene que
    # quedar con la Y grande.
    origen = min(puntos, key=lambda p: p[0] + p[1] * 0)
    assert origen[1] > d.alto / 2


def test_un_dxf_vacio_se_rechaza():
    with pytest.raises(lector.DxfInvalido):
        lector.leer(_fichero(ezdxf.new("R2010")))


def test_basura_se_rechaza():
    with pytest.raises(lector.DxfInvalido):
        lector.leer(b"esto no es un DXF ni de lejos")


def test_el_json_no_repite_las_claves_de_cada_punto():
    """En un plano de veinte mil trazos, escribir «x» e «y» en cada punto
    multiplica por tres lo que va por el cable sin añadir nada."""
    j = lector.a_json(lector.leer(_fichero(_sala())))
    assert isinstance(j["trazos"][0]["p"][0], list)
    assert len(j["trazos"][0]["p"][0]) == 2
