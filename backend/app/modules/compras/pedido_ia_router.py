"""Rutas de "Ayuda con IA" sobre Pedidos de CLIENTE (Fase 4). Aparte de
`pedido_router.py` porque piden además el módulo `ia` activo, mismo motivo
que `obras/ia_router.py`/`facturacion/ia_certificacion.py`: poder leerlas y
desactivarlas juntas.

Solo disponible en pedidos de cliente: un pedido a proveedor no tiene
descompuesto que montar (partida siempre alzada), así que cualquier intento
aquí se rechaza con 409 antes de tocar nada.
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
from app.modules.compras import ia_asistente_pedido as asistente
from app.modules.compras import pedido_service as service
from app.modules.compras.models import Pedido, TipoPedido
from app.modules.compras.pedido_schemas import (
    ConversarAyudaPedido,
    PedidoAplicarCapituloIA,
    PedidoCapituloCreate,
    PedidoMedicionCreate,
    PedidoPartidaCreate,
    PedidoPartidaUpdate,
)
from app.modules.core import auditoria_service
from app.modules.ia.deepseek import DeepSeekError
from app.modules.ia.schemas import RespuestaAyudaLinea
from app.modules.presupuestos import service as banco_service
from app.modules.presupuestos.models import NaturalezaConcepto
from app.modules.presupuestos.schemas import ConceptoCreate

guard = [Depends(require_module("compras")), Depends(require_module("ia"))]
router = APIRouter(prefix="/api/pedidos", tags=["compras"], dependencies=guard)


async def _pedido_cliente_propio(
    session: AsyncSession, pedido_id: uuid.UUID, alcance: Alcance, principal: Principal
) -> Pedido:
    resultado = await service.obtener(session, pedido_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido no encontrado")
    pedido, _razon_social = resultado
    verificar_propiedad(alcance, principal, pedido.creado_por_subject)
    if pedido.tipo != TipoPedido.CLIENTE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El asistente de IA solo está disponible en pedidos de cliente; "
                "este pedido es de proveedor y no tiene descompuesto que montar"
            ),
        )
    return pedido


@router.post("/{pedido_id}/ia/conversar", response_model=RespuestaAyudaLinea)
async def ia_conversar(
    pedido_id: uuid.UUID,
    datos: ConversarAyudaPedido,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> RespuestaAyudaLinea:
    """Un turno de "Ayuda con IA" sobre un pedido de cliente: conversación
    libre con acceso de solo lectura a toda la cuenta (puede buscar en
    cualquier pedido o partida propios) y, si hace falta, termina en una
    propuesta de acción — nunca la ejecuta ella sola, eso lo hace el cliente
    al confirmarla, contra los endpoints de pegar ya existentes."""
    await _pedido_cliente_propio(session, pedido_id, alcance, principal)
    if datos.contexto.pedido_id != pedido_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El contexto no corresponde a este pedido",
        )
    try:
        resultado = await asistente.ayuda_conversar(session, datos, principal)
    except DeepSeekError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except service.DescomposicionNoDisponible as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # Sin escritura propia (la conversación no se guarda), pero sí queda el
    # registro de uso para facturación — se confirma aquí mismo, mismo
    # criterio que `ia.router.ayuda_linea_conversar`.
    await session.commit()
    return RespuestaAyudaLinea(respuesta=resultado.respuesta, propuesta=resultado.propuesta)


@router.post(
    "/{pedido_id}/ia/aplicar-capitulo", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def aplicar_capitulo_ia(
    pedido_id: uuid.UUID,
    datos: PedidoAplicarCapituloIA,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> dict:
    """Como `presupuesto_router.aplicar_capitulo_ia`, pero creando
    `PedidoCapitulo`/`PedidoPartida` (con mediciones y descompuesto) en vez
    de `Capitulo`/`Partida` — solo en pedidos de cliente."""
    pedido = await _pedido_cliente_propio(session, pedido_id, alcance, principal)
    capitulo = await service.crear_capitulo(
        session, pedido_id, PedidoCapituloCreate(resumen=datos.capitulo_resumen)
    )
    assert capitulo is not None

    for orden, partida_datos in enumerate(datos.partidas):
        if partida_datos.partida_id is not None:
            existente = await service.obtener_partida(session, partida_datos.partida_id)
            # No solo que exista y sea de esta cuenta (ya lo comprobó el
            # asistente al proponerlo): tiene que ser DE ESTE pedido.
            if existente is None or existente.pedido_id != pedido_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"La partida {partida_datos.partida_id} no es de este pedido",
                )
            movida = await service.actualizar_partida(
                session,
                partida_datos.partida_id,
                PedidoPartidaUpdate(capitulo_id=capitulo.id, orden=orden),
            )
            assert movida is not None
            continue

        partida = await service.crear_partida(
            session,
            capitulo.id,
            PedidoPartidaCreate(
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
                PedidoMedicionCreate(
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
        tabla=tabla_de(Pedido),
        registro_id=pedido_id,
        organization_id=pedido.organization_id,
        descripcion=(
            f"La IA creó el capítulo «{capitulo.resumen}» con "
            f"{' y '.join(partes_descripcion)}."
        ),
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
    )
    await session.commit()
    return {"id": str(capitulo.id), "resumen": capitulo.resumen, "partidas": total_partidas}
