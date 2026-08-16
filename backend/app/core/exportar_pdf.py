"""PDF genérico de un listado — cualquier pantalla con tabla puede pedirlo
(ver `DataTable.tsx` en el frontend), no solo facturación/presupuestos.

Mismo mecanismo que `facturacion/informes.py`/`presupuestos/informes.py`
(Jinja2 + WeasyPrint dentro del contenedor), pero con datos ya formateados
que manda el propio frontend (columnas visibles, filtradas y ordenadas tal
cual las tiene el usuario en pantalla) en vez de volver a consultar la base
de datos — así el PDF exporta EXACTAMENTE lo que se ve, sin duplicar el
filtrado/orden de cada listado aquí.
"""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

DIRECTORIO_PLANTILLAS = Path(__file__).parent / "plantillas"

# Límite defensivo: esto renderiza en memoria dentro del contenedor de la
# API, no es una cola de trabajo — un listado de decenas de miles de filas
# pedido por error no debe poder colgar el proceso.
MAX_FILAS = 5000
MAX_COLUMNAS = 50


class ExportacionDemasiadoGrande(Exception):
    pass


def generar_pdf_listado(*, titulo: str, columnas: list[str], filas: list[list[str]]) -> bytes:
    from weasyprint import HTML

    if len(filas) > MAX_FILAS:
        raise ExportacionDemasiadoGrande(f"Máximo {MAX_FILAS} filas por exportación (pide {len(filas)})")
    if len(columnas) > MAX_COLUMNAS:
        raise ExportacionDemasiadoGrande(f"Máximo {MAX_COLUMNAS} columnas por exportación")

    entorno = Environment(
        loader=FileSystemLoader(DIRECTORIO_PLANTILLAS),
        autoescape=select_autoescape(["html"]),
    )
    html = entorno.get_template("listado.html").render(
        titulo=titulo,
        columnas=columnas,
        filas=filas,
        total_filas=len(filas),
        generado_en=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
    return HTML(string=html).write_pdf()
