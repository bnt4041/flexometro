"""Ventas de un concepto del banco de precios: presupuestado vs. facturado.

Vive en `facturacion` porque es el único módulo con visibilidad legítima
sobre las dos piezas que hay que cruzar: qué partidas usan el concepto
(`presupuestos`, del que `facturacion` ya depende transitivamente a través de
`obras`) y qué se ha certificado de cada una (`CertificacionLinea`, propio de
este módulo). `presupuestos` no puede importar `facturacion` — la dependencia
va al revés — así que este cruce no puede vivir en el router de conceptos
aunque hable de un concepto; por eso su ruta pública
(`/api/conceptos/{id}/ventas`) se registra desde el router de `facturacion`,
no desde el de `presupuestos` (mismo patrón que `compras/costes.py` con el
informe de coste real de una obra).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redondeo import redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.facturacion.models import Certificacion, CertificacionLinea, EstadoCertificacion
from app.modules.presupuestos.models_presupuesto import Partida
from app.modules.presupuestos.schemas import VentasOut


async def ventas_de_concepto(session: AsyncSession, concepto_id: uuid.UUID) -> VentasOut:
    org_id = require_organization_id()

    partidas, importe_presupuestado = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Partida.importe), 0)).where(
                Partida.concepto_id == concepto_id, Partida.organization_id == org_id
            )
        )
    ).one()

    # Solo certificaciones emitidas: una en borrador todavía puede cambiar de
    # importe y no es "facturado" todavía, es "en curso".
    lineas, importe_facturado = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(CertificacionLinea.importe_periodo), 0))
            .join(Partida, Partida.id == CertificacionLinea.partida_id)
            .join(Certificacion, Certificacion.id == CertificacionLinea.certificacion_id)
            .where(
                Partida.concepto_id == concepto_id,
                CertificacionLinea.organization_id == org_id,
                Certificacion.estado == EstadoCertificacion.EMITIDA,
            )
        )
    ).one()

    return VentasOut(
        presupuestado_partidas=partidas,
        presupuestado_importe=redondear_precio(importe_presupuestado),
        facturado_lineas=lineas,
        facturado_importe=redondear_precio(importe_facturado),
    )
