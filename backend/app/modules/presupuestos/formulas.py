"""Evaluación de fórmulas de medición — Fase 37.

Las fórmulas las escribe el propio usuario ("base * altura / 2"), así que
**no** se puede usar `eval()`: sería ejecutar código arbitrario del cliente en
el servidor, y en una aplicación multi-tenant eso significa que cualquier
usuario podría leer la base de datos entera. Aquí se analiza la expresión con
`ast` y se recorre el árbol admitiendo solo lo que tiene sentido en una
fórmula de geometría: números, variables, los cinco operadores aritméticos y
un puñado de funciones matemáticas. Cualquier otro nodo (llamadas a funciones
desconocidas, atributos, comprensiones, asignaciones...) se rechaza.

El cálculo se hace en `float` porque `sqrt` y `pi` no son exactos en decimal
de todas formas, y el resultado se redondea a la precisión de medición (tres
decimales), que es la que manda en el estado de mediciones.
"""

import ast
import math
from decimal import Decimal

from app.core.redondeo import redondear_medicion

# Funciones permitidas dentro de una fórmula. Nada de `open`, `__import__` ni
# cualquier otra cosa que no sea aritmética de toda la vida.
FUNCIONES = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "radians": math.radians,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
}
CONSTANTES = {"pi": math.pi, "e": math.e}

_OPERADORES_BINARIOS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
)
_OPERADORES_UNARIOS = (ast.UAdd, ast.USub)


class FormulaInvalida(Exception):
    pass


def _arbol(expresion: str) -> ast.Expression:
    if not expresion or not expresion.strip():
        raise FormulaInvalida("La fórmula está vacía")
    if len(expresion) > 500:
        raise FormulaInvalida("La fórmula es demasiado larga (máximo 500 caracteres)")
    try:
        return ast.parse(expresion, mode="eval")
    except SyntaxError as exc:
        raise FormulaInvalida(f"La fórmula no se entiende: {exc.msg}") from exc


def _revisar(nodo: ast.AST) -> None:
    """Recorre el árbol y revienta ante el primer nodo que no sea aritmética."""
    if isinstance(nodo, ast.Expression):
        _revisar(nodo.body)
    elif isinstance(nodo, ast.Constant):
        if not isinstance(nodo.value, (int, float)):
            raise FormulaInvalida("En una fórmula solo caben números")
    elif isinstance(nodo, ast.Name):
        return
    elif isinstance(nodo, ast.BinOp):
        if not isinstance(nodo.op, _OPERADORES_BINARIOS):
            raise FormulaInvalida("Operador no permitido en una fórmula")
        _revisar(nodo.left)
        _revisar(nodo.right)
    elif isinstance(nodo, ast.UnaryOp):
        if not isinstance(nodo.op, _OPERADORES_UNARIOS):
            raise FormulaInvalida("Operador no permitido en una fórmula")
        _revisar(nodo.operand)
    elif isinstance(nodo, ast.Call):
        if not isinstance(nodo.func, ast.Name) or nodo.func.id not in FUNCIONES:
            permitidas = ", ".join(sorted(FUNCIONES))
            raise FormulaInvalida(f"Solo se admiten estas funciones: {permitidas}")
        if nodo.keywords:
            raise FormulaInvalida("Las funciones de una fórmula no admiten argumentos con nombre")
        for argumento in nodo.args:
            _revisar(argumento)
    else:
        raise FormulaInvalida(
            "La fórmula solo puede tener números, variables, operaciones aritméticas y funciones matemáticas"
        )


def validar(expresion: str) -> list[str]:
    """Comprueba que la fórmula es aritmética válida y devuelve sus variables,
    en orden de aparición y sin repetir."""
    arbol = _arbol(expresion)
    _revisar(arbol)

    variables: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and nodo.id not in CONSTANTES:
            # Los nombres de función ya se validan en `_revisar`; aquí se
            # excluyen para que no aparezcan como si fueran variables.
            if nodo.id in FUNCIONES:
                continue
            if nodo.id not in variables:
                variables.append(nodo.id)
    return variables


def evaluar(expresion: str, valores: dict[str, Decimal | float | int]) -> Decimal:
    """Resuelve la fórmula con los valores dados. Las variables que no se
    informen valen 0: es más predecible que fallar a media captura de datos, y
    deja ver el parcial a cero mientras se rellena."""
    arbol = _arbol(expresion)
    _revisar(arbol)

    entorno: dict[str, float] = dict(CONSTANTES)
    for nombre, valor in (valores or {}).items():
        try:
            entorno[str(nombre)] = float(valor)
        except (TypeError, ValueError) as exc:
            raise FormulaInvalida(f"El valor de '{nombre}' no es un número") from exc

    def resolver(nodo: ast.AST) -> float:
        if isinstance(nodo, ast.Expression):
            return resolver(nodo.body)
        if isinstance(nodo, ast.Constant):
            return float(nodo.value)
        if isinstance(nodo, ast.Name):
            if nodo.id in FUNCIONES:
                raise FormulaInvalida(f"'{nodo.id}' es una función, hay que llamarla con paréntesis")
            return entorno.get(nodo.id, 0.0)
        if isinstance(nodo, ast.BinOp):
            izquierda, derecha = resolver(nodo.left), resolver(nodo.right)
            if isinstance(nodo.op, ast.Add):
                return izquierda + derecha
            if isinstance(nodo.op, ast.Sub):
                return izquierda - derecha
            if isinstance(nodo.op, ast.Mult):
                return izquierda * derecha
            if isinstance(nodo.op, ast.Div):
                if derecha == 0:
                    raise FormulaInvalida("La fórmula divide por cero")
                return izquierda / derecha
            if isinstance(nodo.op, ast.Mod):
                if derecha == 0:
                    raise FormulaInvalida("La fórmula divide por cero")
                return izquierda % derecha
            if isinstance(nodo.op, ast.Pow):
                # Un exponente grande cuelga el proceso calculando un número
                # de millones de cifras; se acota antes de intentarlo.
                if abs(derecha) > 64:
                    raise FormulaInvalida("Exponente demasiado grande (máximo 64)")
                return izquierda**derecha
        if isinstance(nodo, ast.UnaryOp):
            valor = resolver(nodo.operand)
            return -valor if isinstance(nodo.op, ast.USub) else valor
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
            try:
                return float(FUNCIONES[nodo.func.id](*[resolver(a) for a in nodo.args]))
            except FormulaInvalida:
                raise
            except Exception as exc:
                raise FormulaInvalida(f"'{nodo.func.id}' no se puede calcular con esos valores") from exc
        raise FormulaInvalida("La fórmula tiene algo que no se puede calcular")

    try:
        resultado = resolver(arbol)
    except OverflowError as exc:
        raise FormulaInvalida("El resultado de la fórmula es demasiado grande") from exc

    if math.isnan(resultado) or math.isinf(resultado):
        raise FormulaInvalida("La fórmula no da un número válido")
    return redondear_medicion(Decimal(str(resultado)))
