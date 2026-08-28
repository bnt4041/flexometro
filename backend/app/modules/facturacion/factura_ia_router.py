"""Rutas de "Ayuda con IA" sobre Facturas de venta (Fase 4). Aparte de
`factura_partidas_router.py`/`router.py` porque piden además el módulo `ia`
activo, mismo motivo que `compras.pedido_ia_router`/`obras/ia_router.py`.

A diferencia de `compras.pedido_ia_router`, una factura de venta es SIEMPRE
de cliente: no hace falta ningún guardián de tipo antes de operar.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.modules.core import auditoria_service
from app.modules.facturacion import factura_partidas_service as service
from app.modules.facturacion import ia_asistente_factura as asistente
from app.modules.facturacion import service as facturacion_service
from app.modules.facturacion.factura_partidas_schemas import (
    ConversarAyudaFactura,
    FacturaAplicarCapituloIA,
    FacturaCapituloCreate,
    FacturaMedicionCreate,
    FacturaPartidaCreate,
    FacturaPartidaUpdate,
)
from app.modules.facturacion.models import Factura
from app.modules.ia.deepseek import DeepSeekError
from app.modules.ia.schemas import RespuestaAyudaLinea
from app.modules.presupuestos import service as banco_service
from app.modules.presupuestos.models import NaturalezaConcepto
from app.modules.presupuestos.schemas import ConceptoCreate

guard = [Depends(require_module("facturacion")), Depends(require_module("ia"))]
router = APIRouter(prefix="/api/facturas", tags=["facturacion"], dependencies=guard)


async def _factura_propia(
    session: AsyncSession, factura_id: uuid.UUID, alcance: Alcance, principal: Principal
) -> Factura:
    resultado = await facturacion_service.obtener_factura(session, factura_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada")
    factura, _razon_social = resultado
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    return factura


@router.post("/{factura_id}/ia/conversar", response_model=RespuestaAyudaLinea)
async def ia_conversar(
    factura_id: uuid.UUID,
    datos: ConversarAyudaFactura,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> RespuestaAyudaLinea:
    """Un turno de "Ayuda con IA" sobre una factura de venta: conversación
    libre con acceso de solo lectura a toda la cuenta (puede buscar en
    cualquier factura o partida propios) y, si hace falta, termina en una
    propuesta de acción — nunca la ejecuta ella sola, eso lo hace el cliente
    al confirmarla, contra los endpoints de pegar ya existentes."""
    await _factura_propia(session, factura_id, alcance, principal)
    if datos.contexto.factura_id != factura_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El contexto no corresponde a esta factura",
        )
    try:
        resultado = await asistente.ayuda_conversar(session, datos, principal)
    except DeepSeekError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    await session.commit()
    return RespuestaAyudaLinea(respuesta=resultado.respuesta, propuesta=resultado.propuesta)


@router.post(
    "/{factura_id}/ia/aplicar-capitulo", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def aplicar_capitulo_ia(
    factura_id: uuid.UUID,
    datos: FacturaAplicarCapituloIA,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> dict:
    """Como `presupuesto_router.aplicar_capitulo_ia`, pero creando
    `FacturaCapitulo`/`FacturaPartida` (con mediciones y descompuesto) en vez
    de `Capitulo`/`Partida`."""
    factura = await _factura_propia(session, factura_id, alcance, principal)
    capitulo = await service.crear_capitulo(
        session, factura_id, FacturaCapituloCreate(resumen=datos.capitulo_resumen)
    )
    assert capitulo is not None

    for orden, partida_datos in enumerate(datos.partidas):
        if partida_datos.partida_id is not None:
            existente = await service.obtener_partida(session, partida_datos.partida_id)
            if existente is None or existente.factura_id != factura_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"La partida {partida_datos.partida_id} no es de esta factura",
                )
            movida = await service.actualizar_partida(
                session,
                partida_datos.partida_id,
                FacturaPartidaUpdate(capitulo_id=capitulo.id, orden=orden),
            )
            assert movida is not None
            continue

        partida = await service.crear_partida(
            session,
            capitulo.id,
            FacturaPartidaCreate(
                resumen=partida_datos.resumen,
                unidad=partida_datos.unidad,
                texto=partida_datos.texto,
                orden=orden,
            ),
        )
        assert partida is not None
        for orden_linea, linea_datos in enumerate(partida_datos.mediciones):
            await service.crear_medicion(
                session,
                partida.id,
                FacturaMedicionCreate(
                    comentario=linea_datos.comentario,
                    uds=linea_datos.uds,
                    longitud=linea_datos.longitud,
                    anchura=linea_datos.anchura,
                    altura=linea_datos.altura,
                    orden=orden_linea,
                ),
            )
        for comp in partida_datos.componentes:
            if comp.personalizado:
                if not comp.resumen or not comp.unidad or comp.precio is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Un componente personalizado necesita resumen, unidad y precio",
                    )
                concepto = await banco_service.crear_concepto(
                    session,
                    ConceptoCreate(
                        tipo="basico",
                        naturaleza=comp.naturaleza or NaturalezaConcepto.SIN_CLASIFICAR,
                        unidad=comp.unidad,
                        resumen=comp.resumen,
                        precio=comp.precio,
                        origen_precio="manual",
                        origen_dato="ia",
                    ),
                )
                hijo_id = concepto.id
            elif comp.concepto_id is not None:
                hijo_id = comp.concepto_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cada componente necesita concepto_id o personalizado",
                )
            try:
                await service.anadir_componente(
                    session, partida.id, hijo_id, comp.rendimiento, Decimal("1")
                )
            except service.ConceptoInvalido as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
                ) from exc

    total_partidas = len(datos.partidas)
    movidas = sum(1 for p in datos.partidas if p.partida_id is not None)
    creadas = total_partidas - movidas
    partes_descripcion = []
    if movidas:
        partes_descripcion.append(
            f"{movidas} partida{'s' if movidas != 1 else ''} movida{'s' if movidas != 1 else ''} aquí"
        )
    if creadas:
        partes_descripcion.append(f"{creadas} partida{'s' if creadas != 1 else ''} nueva{'s' if creadas != 1 else ''}")
    await auditoria_service.registrar_evento(
        session,
        tabla=tabla_de(Factura),
        registro_id=factura_id,
        organization_id=factura.organization_id,
        descripcion=(
            f"La IA creó el capítulo «{capitulo.resumen}» con "
            f"{' y '.join(partes_descripcion)}."
        ),
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
    )
    await session.commit()
    return {"id": str(capitulo.id), "resumen": capitulo.resumen, "partidas": total_partidas}
