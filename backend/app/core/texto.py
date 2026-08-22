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
    return recortado or "empresa"
