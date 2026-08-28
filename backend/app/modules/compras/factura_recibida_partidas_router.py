"""Rutas de capítulos/partidas/mediciones de la Factura recibida (de
proveedor, Fase 2). Aparte de `factura_recibida_router.py`, mismo motivo:
no seguir engordándolo. Sin descomposición ni venta — ver
`factura_recibida_partidas_service.py`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.modules.compras import factura_recibida_partidas_service as service
from app.modules.compras import factura_recibida_service as facturas
from app.modules.compras.factura_recibida_partidas_schemas import (
    FacturaRecibidaCapituloConPartidas,
    FacturaRecibidaCapituloCreate,
    FacturaRecibidaCapituloOut,
    FacturaRecibidaCapituloUpdate,
    FacturaRecibidaMedicionCreate,
    FacturaRecibidaMedicionOut,
    FacturaRecibidaMedicionUpdate,
    FacturaRecibidaPartidaCreate,
    FacturaRecibidaPartidaDetalle,
    FacturaRecibidaPartidaOut,
    FacturaRecibidaPartidaUpdate,
    FacturaRecibidaPegarCapitulos,
    FacturaRecibidaPegarMediciones,
    FacturaRecibidaPegarPartidas,
    FacturaRecibidaResultadoPegado,
)

guard = Depends(require_module("compras"))

facturas_recibidas_capitulos_router = APIRouter(
    prefix="/api/facturas-recibidas-capitulos", tags=["compras"], dependencies=[guard]
)
facturas_recibidas_partidas_router = APIRouter(
    prefix="/api/facturas-recibidas-partidas", tags=["compras"], dependencies=[guard]
)
facturas_recibidas_mediciones_router = APIRouter(
    prefix="/api/facturas-recibidas-mediciones", tags=["compras"], dependencies=[guard]
)
# Prefijo de la creación anidada bajo la factura: `/api/facturas-recibidas`
# ya lo usa `factura_recibida_router.py` para el CRUD de cabecera — se añade
# aquí el único endpoint que falta (`POST .../capitulos`) sin tocar ese
# archivo, igual que se hace en `facturacion.factura_partidas_router`.
facturas_recibidas_router = APIRouter(
    prefix="/api/facturas-recibidas", tags=["compras"], dependencies=[guard]
)


async def _factura_propia(
    session: AsyncSession, factura_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    factura = await facturas.obtener(session, factura_id)
    if factura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada")
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    return factura


@facturas_recibidas_router.get(
    "/{factura_id}/capitulos", response_model=list[FacturaRecibidaCapituloConPartidas]
)
async def listar_capitulos(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[FacturaRecibidaCapituloConPartidas]:
    """El árbol completo de la factura recibida —capítulos, partidas y
    mediciones, sin descomposición— para pintar la ficha de una sola vez."""
    await _factura_propia(session, factura_id, alcance, principal)
    capitulos = await service.cargar_capitulos(session, factura_id)
    resultado = []
    for capitulo in capitulos:
        partidas = [await _partida_detalle_de(session, partida) for partida in capitulo.partidas]
        resultado.append(
            FacturaRecibidaCapituloConPartidas(
                **FacturaRecibidaCapituloOut.model_validate(capitulo).model_dump(), partidas=partidas
            )
        )
    return resultado


@facturas_recibidas_router.post(
    "/{factura_id}/capitulos", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def crear_capitulo(
    factura_id: uuid.UUID,
    datos: FacturaRecibidaCapituloCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> dict:
    await _factura_propia(session, factura_id, alcance, principal)
    capitulo = await service.crear_capitulo(session, factura_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@facturas_recibidas_router.post(
    "/{factura_id}/capitulos/pegar", response_model=FacturaRecibidaResultadoPegado
)
async def pegar_capitulos(
    factura_id: uuid.UUID,
    datos: FacturaRecibidaPegarCapitulos,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaResultadoPegado:
    """Copia o mueve capítulos enteros —con sus partidas y mediciones— a
    esta factura recibida (Fase 5: portapapeles, de la misma factura o de
    otra)."""
    await _factura_propia(session, factura_id, alcance, principal)
    pegados = await service.pegar_capitulos(session, factura_id, datos.capitulo_ids, datos.alcance)
    await session.commit()
    return FacturaRecibidaResultadoPegado(pegadas=pegados)


async def _capitulo_propio(
    session: AsyncSession, capitulo_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    capitulo = await service.obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    await _factura_propia(session, capitulo.factura_id, alcance, principal)
    return capitulo


@facturas_recibidas_capitulos_router.patch("/{capitulo_id}", response_model=dict)
async def actualizar_capitulo(
    capitulo_id: uuid.UUID,
    datos: FacturaRecibidaCapituloUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> dict:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    capitulo = await service.actualizar_capitulo(session, capitulo_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@facturas_recibidas_capitulos_router.delete("/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    await service.eliminar_capitulo(session, capitulo_id)
    await session.commit()


@facturas_recibidas_capitulos_router.post(
    "/{capitulo_id}/partidas",
    response_model=FacturaRecibidaPartidaDetalle,
    status_code=status.HTTP_201_CREATED,
)
async def crear_partida(
    capitulo_id: uuid.UUID,
    datos: FacturaRecibidaPartidaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaPartidaDetalle:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    try:
        partida = await service.crear_partida(session, capitulo_id, datos)
    except service.ConceptoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except service.PartidaSinDatos as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert partida is not None
    await session.commit()
    return await _partida_detalle_de(session, partida)


@facturas_recibidas_capitulos_router.post(
    "/{capitulo_id}/partidas/pegar", response_model=FacturaRecibidaResultadoPegado
)
async def pegar_partidas(
    capitulo_id: uuid.UUID,
    datos: FacturaRecibidaPegarPartidas,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaResultadoPegado:
    """Copia o mueve partidas enteras —con sus mediciones— a este capítulo
    (Fase 5: portapapeles, de la misma factura o de otra)."""
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    pegadas = await service.pegar_partidas(session, capitulo_id, datos.partida_ids, datos.alcance)
    await session.commit()
    return FacturaRecibidaResultadoPegado(pegadas=pegadas)


async def _partida_propia(
    session: AsyncSession, partida_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    partida = await service.obtener_partida(session, partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    await _factura_propia(session, partida.factura_id, alcance, principal)
    return partida


async def _partida_detalle_de(session: AsyncSession, partida) -> FacturaRecibidaPartidaDetalle:
    # `tiene_desglose` no es columna: se calcula aquí a partir de la relación
    # ya cargada (`obtener_partida` la trae con `selectinload`), mismo
    # criterio que `factura_recibida_partidas_service.cargar_capitulos`.
    partida.tiene_desglose = len(partida.mediciones) > 0
    detalle = FacturaRecibidaPartidaDetalle(
        **FacturaRecibidaPartidaOut.model_validate(partida).model_dump(),
        mediciones=[FacturaRecibidaMedicionOut.model_validate(m) for m in partida.mediciones],
    )
    if partida.concepto_id is not None:
        from app.modules.presupuestos.service import obtener_concepto

        concepto = await obtener_concepto(session, partida.concepto_id)
        if concepto is not None and concepto.precio != partida.precio:
            detalle.precio_cuadro = concepto.precio
    return detalle


@facturas_recibidas_partidas_router.get("/{partida_id}", response_model=FacturaRecibidaPartidaDetalle)
async def detalle_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> FacturaRecibidaPartidaDetalle:
    partida = await _partida_propia(session, partida_id, alcance, principal)
    return await _partida_detalle_de(session, partida)


@facturas_recibidas_partidas_router.patch("/{partida_id}", response_model=FacturaRecibidaPartidaOut)
async def actualizar_partida(
    partida_id: uuid.UUID,
    datos: FacturaRecibidaPartidaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaPartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    partida = await service.actualizar_partida(session, partida_id, datos)
    assert partida is not None
    await session.commit()
    return FacturaRecibidaPartidaOut.model_validate(partida)


@facturas_recibidas_partidas_router.delete("/{partida_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _partida_propia(session, partida_id, alcance, principal)
    await service.eliminar_partida(session, partida_id)
    await session.commit()


@facturas_recibidas_partidas_router.post(
    "/{partida_id}/mediciones",
    response_model=FacturaRecibidaMedicionOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_medicion(
    partida_id: uuid.UUID,
    datos: FacturaRecibidaMedicionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaMedicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    medicion = await service.crear_medicion(session, partida_id, datos)
    assert medicion is not None
    await session.commit()
    return FacturaRecibidaMedicionOut.model_validate(medicion)


@facturas_recibidas_partidas_router.post(
    "/{partida_id}/mediciones/pegar", response_model=FacturaRecibidaResultadoPegado
)
async def pegar_mediciones(
    partida_id: uuid.UUID,
    datos: FacturaRecibidaPegarMediciones,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaResultadoPegado:
    """Copia o mueve mediciones sueltas a esta partida (Fase 5)."""
    await _partida_propia(session, partida_id, alcance, principal)
    pegadas = await service.pegar_mediciones(session, partida_id, datos.medicion_ids, datos.alcance)
    await session.commit()
    return FacturaRecibidaResultadoPegado(pegadas=pegadas)


async def _medicion_propia(
    session: AsyncSession, medicion_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    medicion = await service.obtener_medicion(session, medicion_id)
    if medicion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medición no encontrada")
    await _partida_propia(session, medicion.partida_id, alcance, principal)
    return medicion


@facturas_recibidas_mediciones_router.patch("/{medicion_id}", response_model=FacturaRecibidaMedicionOut)
async def actualizar_medicion(
    medicion_id: uuid.UUID,
    datos: FacturaRecibidaMedicionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaMedicionOut:
    await _medicion_propia(session, medicion_id, alcance, principal)
    medicion = await service.actualizar_medicion(session, medicion_id, datos)
    assert medicion is not None
    await session.commit()
    return FacturaRecibidaMedicionOut.model_validate(medicion)


@facturas_recibidas_mediciones_router.delete("/{medicion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_medicion(
    medicion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _medicion_propia(session, medicion_id, alcance, principal)
    await service.eliminar_medicion(session, medicion_id)
    await session.commit()


router = APIRouter()
router.include_router(facturas_recibidas_router)
router.include_router(facturas_recibidas_capitulos_router)
router.include_router(facturas_recibidas_partidas_router)
router.include_router(facturas_recibidas_mediciones_router)
