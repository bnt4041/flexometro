"""De dónde salen los datos de un informe.

Cada fuente declara sus dimensiones (por qué se agrupa) y sus métricas (qué se
cuenta o se suma), más el módulo al que pertenece. Ese último dato es lo que
sostiene todo lo demás: **un informe se ejecuta con el alcance de permisos de
quien lo pide**. Sin eso, un listado agregado sería la puerta trasera perfecta
—«total facturado por cliente» le contaría a cualquiera lo que la pantalla de
facturas le niega—.

Donde solo hay recuentos es porque el importe no está guardado: un
presupuesto o un pedido calculan su total desde sus líneas, y sumarlo aquí
significaría recorrer el descompuesto entero en cada consulta. Se dice en
lugar de inventar una cifra que no cuadre con la ficha.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func


@dataclass(frozen=True)
class Dimension:
    nombre: str
    etiqueta: str
    #: Devuelve la expresión por la que agrupar. Es una función y no la
    #: columna directamente para que el modelo se importe tarde y no cierre
    #: ciclos con los módulos de negocio.
    columna: Callable[[], Any]
    #: `texto` | `mes` — el segundo agrupa una fecha por año-mes.
    tipo: str = "texto"


@dataclass(frozen=True)
class Metrica:
    nombre: str
    etiqueta: str
    agregado: Callable[[], Any]
    #: `numero` | `dinero`. Solo decide cómo se pinta.
    formato: str = "numero"


@dataclass(frozen=True)
class Fuente:
    codigo: str
    #: A qué módulo pertenece. Decide el permiso y el alcance.
    modulo: str
    etiqueta: str
    descripcion: str
    modelo: Callable[[], Any]
    dimensiones: tuple[Dimension, ...]
    metricas: tuple[Metrica, ...]
    #: Columna que dice quién creó el registro, para el alcance «solo los
    #: míos». Sin ella, una fuente NO puede servirse con ese alcance — y se
    #: niega en vez de enseñarlo todo.
    columna_autor: str | None = "creado_por_subject"


_FUENTES: dict[str, Fuente] = {}


def registrar(fuente: Fuente) -> Fuente:
    if fuente.codigo in _FUENTES:
        raise ValueError(f"La fuente «{fuente.codigo}» ya está registrada")
    _FUENTES[fuente.codigo] = fuente
    return fuente


def catalogo() -> list[Fuente]:
    return sorted(_FUENTES.values(), key=lambda f: f.etiqueta)


def obtener(codigo: str) -> Fuente | None:
    return _FUENTES.get(codigo)


def registrar_catalogo_inicial() -> None:
    """Idempotente."""
    if obtener("facturas") is not None:
        return

    def _factura():
        from app.modules.facturacion.models import Factura

        return Factura

    def _obra():
        from app.modules.obras.models import Obra

        return Obra

    def _presupuesto():
        from app.modules.presupuestos.models_presupuesto import Presupuesto

        return Presupuesto

    def _tercero():
        from app.modules.terceros.models import Tercero

        return Tercero

    registrar(
        Fuente(
            codigo="facturas",
            modulo="facturacion",
            etiqueta="Facturas emitidas",
            descripcion="Lo facturado, por serie, estado, mes o cliente.",
            modelo=_factura,
            dimensiones=(
                Dimension("serie", "Serie", lambda: _factura().serie),
                Dimension("estado", "Estado", lambda: _factura().estado),
                Dimension("mes", "Mes de emisión", lambda: _factura().fecha_emision, tipo="mes"),
            ),
            metricas=(
                Metrica("numero", "Nº de facturas", lambda: func.count()),
                Metrica(
                    "base", "Base imponible",
                    lambda: func.coalesce(func.sum(_factura().base_imponible), 0),
                    formato="dinero",
                ),
                Metrica(
                    "total", "Total",
                    lambda: func.coalesce(func.sum(_factura().total), 0),
                    formato="dinero",
                ),
            ),
        )
    )

    registrar(
        Fuente(
            codigo="obras",
            modulo="obras",
            etiqueta="Obras",
            descripcion=(
                "Cuántas obras hay en cada estado. Sin importes: el PEM se "
                "calcula desde el presupuesto, no está guardado en la obra."
            ),
            modelo=_obra,
            dimensiones=(
                Dimension("estado", "Estado", lambda: _obra().estado),
                Dimension("mes", "Mes de inicio", lambda: _obra().fecha_inicio, tipo="mes"),
            ),
            metricas=(Metrica("numero", "Nº de obras", lambda: func.count()),),
        )
    )

    registrar(
        Fuente(
            codigo="presupuestos",
            modulo="presupuestos",
            etiqueta="Presupuestos",
            descripcion=(
                "Cuántos presupuestos por estado, tipo o mes. Sin importes: "
                "el total sale del descompuesto y sumarlo aquí obligaría a "
                "recorrerlo entero en cada consulta."
            ),
            modelo=_presupuesto,
            dimensiones=(
                Dimension("estado", "Estado", lambda: _presupuesto().estado),
                Dimension("tipo", "Tipo", lambda: _presupuesto().tipo),
                Dimension("tipo_obra", "Tipo de obra", lambda: _presupuesto().tipo_obra),
                Dimension(
                    "mes", "Mes de creación", lambda: _presupuesto().created_at, tipo="mes"
                ),
            ),
            metricas=(Metrica("numero", "Nº de presupuestos", lambda: func.count()),),
        )
    )

    registrar(
        Fuente(
            codigo="terceros",
            modulo="terceros",
            etiqueta="Terceros",
            descripcion="Clientes, proveedores y subcontratistas por provincia o país.",
            modelo=_tercero,
            dimensiones=(
                Dimension("provincia", "Provincia", lambda: _tercero().provincia),
                Dimension("pais", "País", lambda: _tercero().pais),
                Dimension("es_cliente", "Es cliente", lambda: _tercero().es_cliente),
                Dimension("es_proveedor", "Es proveedor", lambda: _tercero().es_proveedor),
            ),
            metricas=(Metrica("numero", "Nº de terceros", lambda: func.count()),),
        )
    )
