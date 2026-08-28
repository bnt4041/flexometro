"""Rutas de capítulos/partidas/mediciones/descomposición de la Factura de
venta (Fase 2). Aparte de `router.py`, mismo motivo que
`compras.pedido_router`: no seguir engordando un router ya grande que mezcla
certificaciones/facturas/cobros.

Mismo patrón de propiedad y de "responder con el estado ya recalculado en la
misma transacción, luego `commit()`" que `presupuesto_router.py` (ver los
comentarios allí sobre la carrera lectura-tras-escritura de `get_session`).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.modules.facturacion import factura_partidas_service as service
from app.modules.facturacion import service as facturacion_service
from app.modules.facturacion.factura_partidas_schemas import (
    FacturaCambioNaturalezaComponente,
    FacturaCambioPrecioComponente,
    FacturaCambioRendimientoComponente,
    FacturaCambioResumenComponente,
    FacturaCambioUnidadComponente,
    FacturaCapituloConPartidas,
    FacturaCapituloCreate,
    FacturaCapituloOut,
    FacturaCapituloUpdate,
    FacturaComponenteNuevo,
    FacturaDescomposicionOut,
    FacturaLineaDescomposicionOut,
    FacturaMedicionCreate,
    FacturaMedicionOut,
    FacturaMedicionUpdate,
    FacturaPartidaCreate,
    FacturaPartidaDetalle,
    FacturaPartidaOut,
    FacturaPartidaUpdate,
    FacturaPegarCapitulos,
    FacturaPegarComponentesDescompuesto,
    FacturaPegarMediciones,
    FacturaPegarPartidas,
    FacturaResultadoCambioPrecio,
    FacturaResultadoPegado,
)

guard = Depends(require_module("facturacion"))

facturas_capitulos_router = APIRouter(
    prefix="/api/facturas-capitulos", tags=["facturacion"], dependencies=[guard]
)
facturas_partidas_router = APIRouter(
    prefix="/api/facturas-partidas", tags=["facturacion"], dependencies=[guard]
)
facturas_mediciones_router = APIRouter(
    prefix="/api/facturas-mediciones", tags=["facturacion"], dependencies=[guard]
)


async def _factura_propia(
    session: AsyncSession, factura_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    resultado = await facturacion_service.obtener_factura(session, factura_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada")
    factura, _razon_social = resultado
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    return factura


# Se registra en el router de facturas de venta ya existente
# (`facturacion.router.facturas_router`), así que aquí no hace falta un
# `facturas_router` propio para la creación anidada — se añade allí mismo
# igual que `crear_capitulo` cuelga de `presupuestos_router` en
# `presupuesto_router.py`. Para no tocar más `facturacion/router.py` de lo
# necesario, se expone aquí un router adicional con el mismo prefijo
# `/api/facturas` para el único endpoint anidado bajo la factura.
facturas_router = APIRouter(prefix="/api/facturas", tags=["facturacion"], dependencies=[guard])


@facturas_router.get("/{factura_id}/capitulos", response_model=list[FacturaCapituloConPartidas])
async def listar_capitulos(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> list[FacturaCapituloConPartidas]:
    """El árbol completo de la factura —capítulos, partidas, mediciones y
    descomposición— para pintar la ficha de una sola vez."""
    await _factura_propia(session, factura_id, alcance, principal)
    capitulos = await service.cargar_capitulos(session, factura_id)
    resultado = []
    for capitulo in capitulos:
        partidas = [await _partida_detalle_de(session, partida) for partida in capitulo.partidas]
        resultado.append(
            FacturaCapituloConPartidas(
                **FacturaCapituloOut.model_validate(capitulo).model_dump(), partidas=partidas
            )
        )
    return resultado


@facturas_router.post(
    "/{factura_id}/capitulos", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def crear_capitulo(
    factura_id: uuid.UUID,
    datos: FacturaCapituloCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> dict:
    await _factura_propia(session, factura_id, alcance, principal)
    capitulo = await service.crear_capitulo(session, factura_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@facturas_router.post("/{factura_id}/capitulos/pegar", response_model=FacturaResultadoPegado)
async def pegar_capitulos(
    factura_id: uuid.UUID,
    datos: FacturaPegarCapitulos,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaResultadoPegado:
    """Copia o mueve capítulos enteros —con sus partidas, descompuesto y
    mediciones— a esta factura (Fase 5: portapapeles, de la misma factura o
    de otra)."""
    await _factura_propia(session, factura_id, alcance, principal)
    pegados = await service.pegar_capitulos(session, factura_id, datos.capitulo_ids, datos.alcance)
    await session.commit()
    return FacturaResultadoPegado(pegadas=pegados)


async def _capitulo_propio(
    session: AsyncSession, capitulo_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    capitulo = await service.obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    await _factura_propia(session, capitulo.factura_id, alcance, principal)
    return capitulo


@facturas_capitulos_router.patch("/{capitulo_id}", response_model=dict)
async def actualizar_capitulo(
    capitulo_id: uuid.UUID,
    datos: FacturaCapituloUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> dict:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    capitulo = await service.actualizar_capitulo(session, capitulo_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@facturas_capitulos_router.delete("/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> None:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    await service.eliminar_capitulo(session, capitulo_id)
    await session.commit()


@facturas_capitulos_router.post(
    "/{capitulo_id}/partidas", response_model=FacturaPartidaDetalle, status_code=status.HTTP_201_CREATED
)
async def crear_partida(
    capitulo_id: uuid.UUID,
    datos: FacturaPartidaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaPartidaDetalle:
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


@facturas_capitulos_router.post("/{capitulo_id}/partidas/pegar", response_model=FacturaResultadoPegado)
async def pegar_partidas(
    capitulo_id: uuid.UUID,
    datos: FacturaPegarPartidas,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaResultadoPegado:
    """Copia o mueve partidas enteras —con su descompuesto y sus
    mediciones— a este capítulo (Fase 5: portapapeles, de la misma factura o
    de otra)."""
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    pegadas = await service.pegar_partidas(session, capitulo_id, datos.partida_ids, datos.alcance)
    await session.commit()
    return FacturaResultadoPegado(pegadas=pegadas)


async def _partida_propia(
    session: AsyncSession, partida_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    partida = await service.obtener_partida(session, partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    await _factura_propia(session, partida.factura_id, alcance, principal)
    return partida


async def _partida_detalle_de(session: AsyncSession, partida) -> FacturaPartidaDetalle:
    # `tiene_desglose`/`descomposicion_propia` no son columnas: se calculan
    # aquí a partir de las relaciones ya cargadas (`obtener_partida` las trae
    # con `selectinload`), mismo criterio que `factura_partidas_service.
    # cargar_capitulos`.
    partida.tiene_desglose = len(partida.mediciones) > 0
    partida.descomposicion_propia = len(partida.descomposicion) > 0
    detalle = FacturaPartidaDetalle(
        **FacturaPartidaOut.model_validate(partida).model_dump(),
        mediciones=[FacturaMedicionOut.model_validate(m) for m in partida.mediciones],
    )
    if partida.concepto_id is not None:
        from app.modules.presupuestos.service import obtener_concepto

        concepto = await obtener_concepto(session, partida.concepto_id)
        if concepto is not None and concepto.precio != partida.precio:
            detalle.precio_cuadro = concepto.precio
    return detalle


@facturas_partidas_router.get("/{partida_id}", response_model=FacturaPartidaDetalle)
async def detalle_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> FacturaPartidaDetalle:
    partida = await _partida_propia(session, partida_id, alcance, principal)
    return await _partida_detalle_de(session, partida)


@facturas_partidas_router.patch("/{partida_id}", response_model=FacturaPartidaOut)
async def actualizar_partida(
    partida_id: uuid.UUID,
    datos: FacturaPartidaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaPartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    partida = await service.actualizar_partida(session, partida_id, datos)
    assert partida is not None
    await session.commit()
    return FacturaPartidaOut.model_validate(partida)


@facturas_partidas_router.delete("/{partida_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> None:
    await _partida_propia(session, partida_id, alcance, principal)
    await service.eliminar_partida(session, partida_id)
    await session.commit()


@facturas_partidas_router.get("/{partida_id}/descomposicion", response_model=FacturaDescomposicionOut)
async def descomposicion_de_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "ver")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    resultado = await service.descomposicion_de_partida(session, partida_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    propia, lineas = resultado
    return FacturaDescomposicionOut(
        propia=propia, lineas=[FacturaLineaDescomposicionOut(**linea) for linea in lineas]
    )


async def _descomposicion_fresca(session: AsyncSession, partida_id: uuid.UUID) -> FacturaDescomposicionOut:
    resultado = await service.descomposicion_de_partida(session, partida_id)
    lineas = [] if resultado is None else resultado[1]
    return FacturaDescomposicionOut(
        propia=bool(resultado and resultado[0]),
        lineas=[FacturaLineaDescomposicionOut(**linea) for linea in lineas],
    )


@facturas_partidas_router.post(
    "/{partida_id}/descomposicion",
    response_model=FacturaDescomposicionOut,
    status_code=status.HTTP_201_CREATED,
)
async def anadir_componente(
    partida_id: uuid.UUID,
    datos: FacturaComponenteNuevo,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        creado = await service.anadir_componente(
            session, partida_id, datos.hijo_id, datos.rendimiento, datos.factor
        )
    except service.ConceptoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not creado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.post(
    "/{partida_id}/descomposicion/independizar", response_model=FacturaDescomposicionOut
)
async def independizar_descomposicion_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    partida = await _partida_propia(session, partida_id, alcance, principal)
    await service.independizar_descomposicion(session, partida)
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.delete(
    "/{partida_id}/descomposicion/{linea_id}", response_model=FacturaDescomposicionOut
)
async def quitar_componente(
    partida_id: uuid.UUID,
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.quitar_componente(session, partida_id, linea_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.patch(
    "/{partida_id}/descomposicion/precio", response_model=FacturaResultadoCambioPrecio
)
async def cambiar_precio_componente(
    partida_id: uuid.UUID,
    datos: FacturaCambioPrecioComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaResultadoCambioPrecio:
    await _partida_propia(session, partida_id, alcance, principal)
    afectadas = await service.cambiar_precio_componente(
        session, partida_id, datos.hijo_id, datos.precio, datos.alcance
    )
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return FacturaResultadoCambioPrecio(partidas_afectadas=afectadas, descomposicion=salida)


@facturas_partidas_router.patch(
    "/{partida_id}/descomposicion/rendimiento", response_model=FacturaDescomposicionOut
)
async def cambiar_rendimiento_componente(
    partida_id: uuid.UUID,
    datos: FacturaCambioRendimientoComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_rendimiento_componente(
        session, partida_id, datos.hijo_id, datos.rendimiento
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.patch(
    "/{partida_id}/descomposicion/resumen", response_model=FacturaDescomposicionOut
)
async def cambiar_resumen_componente(
    partida_id: uuid.UUID,
    datos: FacturaCambioResumenComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_resumen_componente(
        session, partida_id, datos.hijo_id, datos.resumen
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.patch(
    "/{partida_id}/descomposicion/naturaleza", response_model=FacturaDescomposicionOut
)
async def cambiar_naturaleza_componente(
    partida_id: uuid.UUID,
    datos: FacturaCambioNaturalezaComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_naturaleza_componente(
        session, partida_id, datos.hijo_id, datos.naturaleza
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.patch(
    "/{partida_id}/descomposicion/unidad", response_model=FacturaDescomposicionOut
)
async def cambiar_unidad_componente(
    partida_id: uuid.UUID,
    datos: FacturaCambioUnidadComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaDescomposicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_unidad_componente(
        session, partida_id, datos.hijo_id, datos.unidad
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@facturas_partidas_router.post("/{partida_id}/descomposicion/pegar", response_model=FacturaResultadoPegado)
async def pegar_componentes(
    partida_id: uuid.UUID,
    datos: FacturaPegarComponentesDescompuesto,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaResultadoPegado:
    """Copia o mueve componentes de un descompuesto a esta partida (Fase 5),
    independizándola del banco de precios si aún lo heredaba."""
    await _partida_propia(session, partida_id, alcance, principal)
    pegadas = await service.pegar_componentes_descompuesto(
        session, partida_id, datos.linea_ids, datos.alcance
    )
    await session.commit()
    return FacturaResultadoPegado(pegadas=pegadas)


@facturas_partidas_router.post(
    "/{partida_id}/mediciones", response_model=FacturaMedicionOut, status_code=status.HTTP_201_CREATED
)
async def crear_medicion(
    partida_id: uuid.UUID,
    datos: FacturaMedicionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaMedicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    medicion = await service.crear_medicion(session, partida_id, datos)
    assert medicion is not None
    await session.commit()
    return FacturaMedicionOut.model_validate(medicion)


@facturas_partidas_router.post("/{partida_id}/mediciones/pegar", response_model=FacturaResultadoPegado)
async def pegar_mediciones(
    partida_id: uuid.UUID,
    datos: FacturaPegarMediciones,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaResultadoPegado:
    """Copia o mueve mediciones sueltas a esta partida (Fase 5)."""
    await _partida_propia(session, partida_id, alcance, principal)
    pegadas = await service.pegar_mediciones(session, partida_id, datos.medicion_ids, datos.alcance)
    await session.commit()
    return FacturaResultadoPegado(pegadas=pegadas)


async def _medicion_propia(
    session: AsyncSession, medicion_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    medicion = await service.obtener_medicion(session, medicion_id)
    if medicion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medición no encontrada")
    await _partida_propia(session, medicion.partida_id, alcance, principal)
    return medicion


@facturas_mediciones_router.patch("/{medicion_id}", response_model=FacturaMedicionOut)
async def actualizar_medicion(
    medicion_id: uuid.UUID,
    datos: FacturaMedicionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> FacturaMedicionOut:
    await _medicion_propia(session, medicion_id, alcance, principal)
    medicion = await service.actualizar_medicion(session, medicion_id, datos)
    assert medicion is not None
    await session.commit()
    return FacturaMedicionOut.model_validate(medicion)


@facturas_mediciones_router.delete("/{medicion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_medicion(
    medicion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> None:
    await _medicion_propia(session, medicion_id, alcance, principal)
    await service.eliminar_medicion(session, medicion_id)
    await session.commit()


router = APIRouter()
router.include_router(facturas_router)
router.include_router(facturas_capitulos_router)
router.include_router(facturas_partidas_router)
router.include_router(facturas_mediciones_router)
