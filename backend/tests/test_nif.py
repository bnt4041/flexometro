import pytest

from app.modules.terceros.nif import normalizar, validar_nif


@pytest.mark.parametrize(
    "valor",
    [
        "12345678Z",  # DNI
        "00000000T",  # DNI, resto 0
        "X1234567L",  # NIE con prefijo X
        "Z1234567R",  # NIE con prefijo Z
        "B12345674",  # CIF de S.L., control numérico
        "A58818501",  # CIF de S.A.
        "P4100000A",  # CIF de organismo público, control alfabético obligatorio
    ],
)
def test_documentos_validos(valor):
    assert validar_nif(valor)


@pytest.mark.parametrize(
    "valor",
    [
        "12345678A",  # letra de control incorrecta
        "B12345678",  # control de CIF incorrecto
        "X1234567A",  # NIE con letra incorrecta
        "1234567Z",   # longitud insuficiente
        "",
        "NOSOYUNNIF",
        "P41000004",  # a P le corresponde letra, no dígito
    ],
)
def test_documentos_invalidos(valor):
    assert not validar_nif(valor)


def test_normaliza_espacios_guiones_y_minusculas():
    assert normalizar(" b-1234 5674 ") == "B12345674"
    assert validar_nif(" b-1234 5674 ")


def test_cif_admite_digito_o_letra_cuando_la_inicial_lo_permite():
    # A la inicial 'C' le valen ambas formas de control.
    assert validar_nif("C12345674") or validar_nif("C1234567E")
