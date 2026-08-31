"""Resolver `{{ nodo.campo }}` con los datos que ha producido el flujo.

Un flujo lo escribe cualquiera desde el navegador, así que esto NUNCA evalúa
código: solo navega por diccionarios con una ruta de puntos. Un `eval()` aquí
sería dar ejecución remota a cualquier usuario de cualquier organización, que
es el fallo más caro que puede tener una herramienta de este tipo.
"""

import re
from typing import Any

#: `{{ algo.con.puntos }}`, con espacios opcionales.
_EXPRESION = re.compile(r"\{\{\s*([\w.\-]+)\s*\}\}")


def _buscar(contexto: dict, ruta: str) -> Any:
    """Navega `a.b.c` por diccionarios y listas. `None` si se pierde."""
    actual: Any = contexto
    for trozo in ruta.split("."):
        if isinstance(actual, dict):
            actual = actual.get(trozo)
        elif isinstance(actual, list) and trozo.isdigit():
            indice = int(trozo)
            actual = actual[indice] if indice < len(actual) else None
        else:
            return None
        if actual is None:
            return None
    return actual


def resolver(valor: Any, contexto: dict) -> Any:
    """Sustituye las expresiones de un valor.

    Si el texto es EXACTAMENTE una expresión (`"{{ x.y }}"`), devuelve el
    valor con su tipo original: un número sigue siendo número y una lista
    sigue siendo lista. Solo cuando la expresión va mezclada con más texto
    (`"Hola {{ x.nombre }}"`) se convierte a cadena — que es justo lo que se
    espera en cada caso.
    """
    if isinstance(valor, dict):
        return {k: resolver(v, contexto) for k, v in valor.items()}
    if isinstance(valor, list):
        return [resolver(v, contexto) for v in valor]
    if not isinstance(valor, str):
        return valor

    entero = _EXPRESION.fullmatch(valor.strip())
    if entero:
        return _buscar(contexto, entero.group(1))

    return _EXPRESION.sub(
        lambda m: "" if (v := _buscar(contexto, m.group(1))) is None else str(v), valor
    )


def referencias(valor: Any) -> set[str]:
    """Qué rutas usa un valor. Sirve para avisar en el editor de que un nodo
    apunta a otro que ya no existe."""
    if isinstance(valor, dict):
        return set().union(*(referencias(v) for v in valor.values())) if valor else set()
    if isinstance(valor, list):
        return set().union(*(referencias(v) for v in valor)) if valor else set()
    if isinstance(valor, str):
        return set(_EXPRESION.findall(valor))
    return set()
