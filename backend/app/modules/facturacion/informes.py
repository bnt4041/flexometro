"""Documentos PDF de facturación: factura y certificación.

Mismo mecanismo que `core/exportar_pdf.py` (Jinja2 + WeasyPrint dentro del
contenedor), con una plantilla propia de este módulo: cada módulo es dueño
de su papelería, no se comparte `base.html` entre dominios distintos.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TIPO_IVA_PORCENTAJE
from app.modules.facturacion import service
from app.modules.facturacion.models import Certificacion, Factura

DIRECTORIO_PLANTILLAS = Path(__file__).parent / "plantillas"


def _formato_es(valor: Any, decimales: int) -> str:
    if valor is None:
        return ""
    numero = Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales))
    entero, _, fraccion = f"{abs(numero):.{decimales}f}".partition(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    texto = ".".join(grupos)
    if decimales:
        texto = f"{texto},{fraccion}"
    return f"-{texto}" if numero < 0 else texto


def _entorno() -> Environment:
    entorno = Environment(
        loader=FileSystemLoader(DIRECTORIO_PLANTILLAS),
        autoescape=select_autoescape(["html"]),
    )
    entorno.filters["eur"] = lambda v: _formato_es(v, 2)
    entorno.filters["num"] = _formato_es
    return entorno


async def generar_factura(session: AsyncSession, factura: Factura, razon_social: str) -> bytes:
    from weasyprint import HTML

    from app.modules.obras.service import obtener_obra
    from app.modules.terceros.models import Tercero

    cliente = await session.get(Tercero, factura.cliente_id)
    obra = await obtener_obra(session, factura.obra_id)

    porcentaje = TIPO_IVA_PORCENTAJE[factura.tipo_iva]
    html = _entorno().get_template("factura.html").render(
        titulo="Factura",
        codigo=factura.codigo,
        factura=factura,
        cliente=cliente,
        obra_codigo=obra.codigo if obra else "",
        obra_nombre=obra.nombre if obra else "",
        etiqueta_iva=f"{porcentaje} %",
    )
    return HTML(string=html).write_pdf()


async def generar_certificacion(session: AsyncSession, certificacion: Certificacion) -> bytes:
    from weasyprint import HTML

    from app.modules.obras.service import obtener_obra

    obra = await obtener_obra(session, certificacion.obra_id)
    importes = service.importes_certificacion(certificacion)

    html = _entorno().get_template("certificacion.html").render(
        titulo="Certificación",
        codigo=certificacion.codigo,
        certificacion=certificacion,
        obra_codigo=obra.codigo if obra else "",
        obra_nombre=obra.nombre if obra else "",
        importes=importes,
    )
    return HTML(string=html).write_pdf()
