"""Aviso a n8n cuando se emite una factura.

Este módulo no habla con la AEAT ni genera Facturae/Veri*Factu — eso exige
certificado digital y registro previo, y es responsabilidad del flujo de n8n
que el propio despliegue configure. Lo único que hace esta pieza es publicar
un payload con todo lo necesario para que ese flujo exista: quién emite, a
quién, qué número de serie, por cuánto y con qué IVA.

El envío es best-effort a propósito: el estado fiscal de la factura (emitida,
numerada) no depende de que n8n esté disponible en ese instante. Si falla,
`notificado_n8n_en` se queda a NULL y la factura aparece como pendiente de
enviar; hay una acción explícita para reintentarlo.
"""

import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.facturacion.models import Factura

logger = logging.getLogger(__name__)


async def notificar_emision(session: AsyncSession, factura: Factura) -> bool:
    """Intenta avisar a n8n. Devuelve si se ha podido notificar."""
    settings = get_settings()
    if not settings.n8n_webhook_facturas_url:
        logger.info(
            "N8N_WEBHOOK_FACTURAS_URL no está configurada; factura %s queda "
            "pendiente de enviar a Veri*Factu/Facturae",
            factura.codigo,
        )
        return False

    from app.modules.terceros.models import Tercero

    cliente = await session.get(Tercero, factura.cliente_id)
    payload = _payload(factura, cliente)

    try:
        async with httpx.AsyncClient(timeout=10.0) as cliente_http:
            respuesta = await cliente_http.post(
                settings.n8n_webhook_facturas_url, json=payload
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("No se pudo notificar la factura %s a n8n: %s", factura.codigo, exc)
        return False

    factura.notificado_n8n_en = datetime.now(UTC)
    await session.flush()
    return True


def _payload(factura: Factura, cliente) -> dict:
    """Datos suficientes para que el flujo de n8n arme el registro Veri*Factu
    o el XML Facturae sin tener que volver a consultar la API."""
    return {
        "factura_id": str(factura.id),
        "codigo_interno": factura.codigo,
        "serie": factura.serie,
        "numero": factura.numero,
        "fecha_emision": factura.fecha_emision.isoformat() if factura.fecha_emision else None,
        "cliente": {
            "id": str(cliente.id) if cliente else None,
            "nif": cliente.nif if cliente else None,
            "razon_social": cliente.razon_social if cliente else None,
        },
        "concepto": factura.concepto,
        "base_imponible": str(factura.base_imponible),
        "tipo_iva": factura.tipo_iva.value,
        "inversion_sujeto_pasivo": factura.inversion_sujeto_pasivo,
        "cuota_iva": str(factura.cuota_iva),
        "total": str(factura.total),
    }
