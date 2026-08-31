"""Qué objetos puede consultar el copiloto, y por qué columnas.

Es una lista blanca a propósito. La alternativa —dejar que el modelo escriba
la consulta— convierte cualquier despiste suyo en una fuga de datos, y encima
salta el alcance «solo los míos», que vive en Python y no en el SQL que él
escribiría. Aquí solo se puede leer lo que está declarado, por las columnas
declaradas, con el filtro de autor puesto por el servidor.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TipoObjeto:
    codigo: str
    modulo: str
    etiqueta: str
    #: Import tardío: si no, este módulo cerraría un ciclo con medio backend.
    modelo: Callable[[], Any]
    #: Por dónde se busca cuando la persona escribe un texto suelto.
    busqueda: tuple[str, ...]
    #: Qué columnas se devuelven. Las que no estén aquí no salen nunca, y eso
    #: incluye las que ni el modelo ni el usuario necesitan (notas internas,
    #: claves ajenas sin sentido fuera de la ficha).
    resumen: tuple[str, ...]
    #: Ruta de la ficha, para que el copiloto pueda enlazarla.
    ruta: str
    columna_autor: str | None = "creado_por_subject"


_TIPOS: dict[str, TipoObjeto] = {}


def registrar(tipo: TipoObjeto) -> TipoObjeto:
    if tipo.codigo in _TIPOS:
        raise ValueError(f"El tipo «{tipo.codigo}» ya está registrado")
    _TIPOS[tipo.codigo] = tipo
    return tipo


def obtener(codigo: str) -> TipoObjeto | None:
    return _TIPOS.get(codigo)


def catalogo() -> list[TipoObjeto]:
    return sorted(_TIPOS.values(), key=lambda t: t.codigo)


def registrar_catalogo_inicial() -> None:
    """Idempotente: el registro de módulos puede llamarse más de una vez."""
    if obtener("obra") is not None:
        return

    def _obra():
        from app.modules.obras.models import Obra

        return Obra

    def _tercero():
        from app.modules.terceros.models import Tercero

        return Tercero

    def _presupuesto():
        from app.modules.presupuestos.models_presupuesto import Presupuesto

        return Presupuesto

    def _factura():
        from app.modules.facturacion.models import Factura

        return Factura

    def _pedido():
        from app.modules.compras.models import Pedido

        return Pedido

    def _albaran():
        from app.modules.compras.models import Albaran

        return Albaran

    registrar(
        TipoObjeto(
            codigo="obra",
            modulo="obras",
            etiqueta="Obra",
            modelo=_obra,
            busqueda=("codigo", "nombre"),
            resumen=(
                "id",
                "codigo",
                "nombre",
                "estado",
                "fecha_inicio",
                "fecha_fin_prevista",
            ),
            ruta="/obras/{id}",
        )
    )
    registrar(
        TipoObjeto(
            codigo="tercero",
            modulo="terceros",
            etiqueta="Tercero (cliente, proveedor o subcontratista)",
            modelo=_tercero,
            busqueda=("codigo", "razon_social", "nombre_comercial", "nif"),
            resumen=(
                "id",
                "codigo",
                "razon_social",
                "nif",
                "es_cliente",
                "es_proveedor",
                "es_subcontratista",
                "email",
                "telefono",
                "ciudad",
                "activo",
            ),
            ruta="/terceros/{id}",
        )
    )
    registrar(
        TipoObjeto(
            codigo="presupuesto",
            modulo="presupuestos",
            etiqueta="Presupuesto de cliente",
            modelo=_presupuesto,
            busqueda=("codigo", "nombre", "emplazamiento"),
            resumen=(
                "id",
                "codigo",
                "nombre",
                "estado",
                "fecha",
                "version",
                "es_plantilla",
                "tipo_obra",
            ),
            ruta="/presupuestos/{id}",
        )
    )
    registrar(
        TipoObjeto(
            codigo="factura",
            modulo="facturacion",
            etiqueta="Factura emitida",
            modelo=_factura,
            busqueda=("codigo", "concepto"),
            resumen=(
                "id",
                "codigo",
                "concepto",
                "fecha_emision",
                "fecha_vencimiento",
                "base_imponible",
                "cuota_iva",
                "total",
                "estado",
            ),
            ruta="/facturas/{id}",
        )
    )
    registrar(
        TipoObjeto(
            codigo="pedido",
            modulo="compras",
            etiqueta="Pedido",
            modelo=_pedido,
            busqueda=("codigo",),
            resumen=("id", "codigo", "fecha", "fecha_entrega_prevista", "estado", "tipo"),
            ruta="/pedidos/{id}",
        )
    )
    registrar(
        TipoObjeto(
            codigo="albaran",
            modulo="compras",
            etiqueta="Albarán",
            modelo=_albaran,
            busqueda=("codigo", "numero_proveedor"),
            resumen=("id", "codigo", "numero_proveedor", "fecha", "estado", "tipo"),
            ruta="/albaranes/{id}",
        )
    )
