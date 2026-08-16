import uuid
from decimal import Decimal

import pytest

from app.modules.ia.deepseek import DeepSeekError, _parsear_respuesta
from app.modules.ia.estadisticas import _agregar
from app.modules.ia.gemini import GeminiError
from app.modules.ia.gemini import _parsear_respuesta as _parsear_respuesta_gemini
from app.modules.ia.medicion import _lineas_out
from app.modules.ia.schemas import LineaSugeridaLLM


# --- Agregación de estadísticas (pura, sin sesión de BD) ---


def test_agregar_cuenta_capitulos_por_resumen_normalizado():
    filas_capitulos = [("Cimentación",), ("cimentación",), ("  CIMENTACIÓN  ",), ("Cubierta",)]
    stats = _agregar(filas_capitulos, [], total_presupuestos=3, generico=False)

    assert stats.total_presupuestos == 3
    assert not stats.generico
    assert stats.capitulos[0].resumen == "Cimentación"
    assert stats.capitulos[0].veces == 3
    assert stats.capitulos[1].resumen == "Cubierta"
    assert stats.capitulos[1].veces == 1


def test_agregar_cuenta_partidas_por_concepto_id():
    concepto_a = uuid.uuid4()
    concepto_b = uuid.uuid4()
    filas_partidas = [
        (concepto_a, "U00001", "Fábrica de ladrillo", "m2"),
        (concepto_a, "U00001", "Fábrica de ladrillo", "m2"),
        (concepto_b, "U00002", "Solera de hormigón", "m2"),
    ]
    stats = _agregar([], filas_partidas, total_presupuestos=2, generico=False)

    assert stats.partidas[0].concepto_id == concepto_a
    assert stats.partidas[0].veces == 2
    assert stats.partidas[1].concepto_id == concepto_b
    assert stats.partidas[1].veces == 1


def test_agregar_respeta_los_topes_de_frecuentes():
    filas_capitulos = [(f"Capítulo {i}",) for i in range(20)]
    stats = _agregar(filas_capitulos, [], total_presupuestos=1, generico=True)
    assert len(stats.capitulos) == 15
    assert stats.generico


def test_agregar_sin_datos_no_revienta():
    stats = _agregar([], [], total_presupuestos=0, generico=True)
    assert stats.capitulos == []
    assert stats.partidas == []


# --- Parseo defensivo de la respuesta de DeepSeek (sin red) ---


def test_parsear_respuesta_valida():
    contenido = """
    {"capitulos": [
        {"resumen": "Cimentación", "partidas": [
            {"codigo_existente": "U00001", "resumen": "Zapata", "unidad": "m3", "es_nueva": false}
        ]}
    ]}
    """
    respuesta = _parsear_respuesta(contenido)
    assert len(respuesta.capitulos) == 1
    assert respuesta.capitulos[0].resumen == "Cimentación"
    assert respuesta.capitulos[0].partidas[0].codigo_existente == "U00001"


def test_parsear_respuesta_json_invalido():
    with pytest.raises(DeepSeekError):
        _parsear_respuesta("esto no es json")


def test_parsear_respuesta_esquema_incorrecto():
    with pytest.raises(DeepSeekError):
        _parsear_respuesta('{"capitulos": "no es una lista"}')


def test_parsear_respuesta_capitulos_vacios_es_valido():
    respuesta = _parsear_respuesta('{"capitulos": []}')
    assert respuesta.capitulos == []


# --- Parseo defensivo de la respuesta de Gemini (sin red) ---


def test_parsear_respuesta_gemini_valida():
    contenido = """
    {"lineas": [
        {"comentario": "Dormitorio 1", "longitud": 4.2, "altura": 2.5}
    ], "observaciones": "El alzado lateral no es legible"}
    """
    respuesta = _parsear_respuesta_gemini(contenido)
    assert len(respuesta.lineas) == 1
    assert respuesta.lineas[0].comentario == "Dormitorio 1"
    assert respuesta.lineas[0].longitud == Decimal("4.2")
    assert respuesta.observaciones == "El alzado lateral no es legible"


def test_parsear_respuesta_gemini_json_invalido():
    with pytest.raises(GeminiError):
        _parsear_respuesta_gemini("esto no es json")


def test_parsear_respuesta_gemini_esquema_incorrecto():
    with pytest.raises(GeminiError):
        _parsear_respuesta_gemini('{"lineas": "no es una lista"}')


def test_parsear_respuesta_gemini_sin_lineas_es_valido():
    respuesta = _parsear_respuesta_gemini('{"lineas": []}')
    assert respuesta.lineas == []


# --- Cálculo local del parcial de las líneas sugeridas (nunca del LLM) ---


def test_lineas_out_calcula_parcial_localmente():
    lineas = [LineaSugeridaLLM(comentario="Muro norte", longitud=Decimal("5"), altura=Decimal("2.5"))]
    salida = _lineas_out(lineas)
    assert salida[0].parcial == Decimal("12.500")


def test_lineas_out_uds_sola_no_vale_cero():
    lineas = [LineaSugeridaLLM(comentario="Puertas", uds=Decimal("3"))]
    salida = _lineas_out(lineas)
    assert salida[0].parcial == Decimal("3.000")


def test_lineas_out_sin_dimensiones_es_cero():
    lineas = [LineaSugeridaLLM(comentario="Sin cotas legibles")]
    salida = _lineas_out(lineas)
    assert salida[0].parcial == Decimal("0.000")
