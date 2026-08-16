"""Validación de NIF/NIE/CIF españoles.

Se valida el dígito de control, no solo el formato: un NIF mal tecleado que
llega a una factura es un problema con Hacienda, y en Fase 7 estos mismos datos
alimentan Veri*Factu.
"""

import re

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_PREFIJO_NIE = {"X": "0", "Y": "1", "Z": "2"}
_LETRAS_CIF = "JABCDEFGHI"
# Organizaciones que siempre llevan letra de control en lugar de dígito.
_CIF_SOLO_LETRA = set("PQRSNW")
# Organizaciones que siempre llevan dígito.
_CIF_SOLO_DIGITO = set("ABEH")

_RE_DNI = re.compile(r"^\d{8}[A-Z]$")
_RE_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")
_RE_CIF = re.compile(r"^[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]$")


def normalizar(valor: str) -> str:
    return valor.strip().upper().replace("-", "").replace(" ", "")


def validar_nif(valor: str) -> bool:
    """True si es un DNI, NIE o CIF con dígito de control correcto."""
    nif = normalizar(valor)
    if _RE_DNI.match(nif):
        return nif[8] == _LETRAS_DNI[int(nif[:8]) % 23]
    if _RE_NIE.match(nif):
        numero = _PREFIJO_NIE[nif[0]] + nif[1:8]
        return nif[8] == _LETRAS_DNI[int(numero) % 23]
    if _RE_CIF.match(nif):
        return _validar_cif(nif)
    return False


def _validar_cif(cif: str) -> bool:
    digitos = cif[1:8]
    # Posiciones pares (índice 1, 3, 5 dentro de los siete dígitos) se suman
    # tal cual; las impares se duplican y se suman sus cifras.
    suma_pares = sum(int(digitos[i]) for i in (1, 3, 5))
    suma_impares = 0
    for i in (0, 2, 4, 6):
        doble = int(digitos[i]) * 2
        suma_impares += doble // 10 + doble % 10

    control = (10 - (suma_pares + suma_impares) % 10) % 10
    esperado_digito = str(control)
    esperado_letra = _LETRAS_CIF[control]

    dado = cif[8]
    inicial = cif[0]
    if inicial in _CIF_SOLO_LETRA:
        return dado == esperado_letra
    if inicial in _CIF_SOLO_DIGITO:
        return dado == esperado_digito
    return dado in (esperado_digito, esperado_letra)
