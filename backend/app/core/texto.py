"""Utilidades de texto de propósito general."""

import re
import unicodedata


def slugify(texto: str, *, max_len: int = 64) -> str:
    """De un nombre libre a un slug válido: minúsculas, sin acentos ni
    símbolos, palabras separadas por un guion — mismo alfabeto que exige
    Keycloak para el atributo `organizacion` (ver `KeycloakAuthBackend`)."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    con_guiones = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")
    recortado = con_guiones[:max_len].strip("-")
    if not recortado:
        return "empresa"
    # Dos caracteres como mínimo: es lo que exigía la validación de cuando el
    # slug se tecleaba a mano, y al pasar a generarlo se perdió sin querer. Un
    # nombre de una sola letra es raro, pero produciría un slug que el realm
    # podría no aceptar, y eso reventaría en el alta y no aquí.
    return recortado if len(recortado) >= 2 else f"{recortado}-1"
