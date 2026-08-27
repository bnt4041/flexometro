"""Rutas del árbol de obra.

Aparte de `router.py` porque son muchas y no tienen nada que ver con la ficha
de la obra: se leen y se prueban mejor juntas.

Las URL son hermanas de las de presupuestos pero no las mismas
(`/api/obra-capitulos/…` frente a `/api/capitulos/…`), a propósito: son tablas
distintas y confundirlas al depurar sale caro.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.modules.obras import arbol_service, service
from app.modules.obras.models import CapituloObra, MedicionObra, PartidaObra, TipoVinculo
from app.modules.obras.schemas import (
    ArbolObraOut,
    CapituloObraCreate,
    CapituloObraOut,
    CapituloObraUpdate,
    MedicionObraCreate,
    MedicionObraOut,
    MedicionObraUpdate,
    NodoObraOut,
    PartidaObraCreate,
    PartidaObraDetalle,
    PartidaObraOut,
    PartidaObraUpdate,
    TotalesObraOut,
)
from app.modules.presupuestos.models_presupuesto import Presupuesto

guard = Depends(require_module("obras"))

arbol_router = APIRouter(prefix="/api/obras", tags=["obras"], dependencies=[guard])
capitulos_router = APIRouter(
    prefix="/api/obra-capitulos", tags=["obras"], dependencies=[guard]
)
partidas_router = APIRouter(
    prefix="/api/obra-partidas", tags=["obras"], dependencies=[guard]
)
mediciones_router = APIRouter(
    prefix="/api/obra-mediciones", tags=["obras"], dependencies=[guard]
)


async def _codigos_de_origen(
    session: AsyncSession, obra_id: uuid.UUID
) -> dict[uuid.UUID, str]:
    """`presupuesto_id → código`, de una vez para todo el árbol.

    La rejilla enseña la procedencia en cada fila; resolverla por fila serían
    tantas consultas como partidas.
    """
    filas = (
        await session.execute(
            select(Presupuesto.id, Presupuesto.codigo).where(
                Presupuesto.id.in_(
                    select(CapituloObra.origen_presupuesto_id)
                    .where(CapituloObra.obra_id == obra_id)
                    .union(
                        select(PartidaObra.origen_presupuesto_id).where(
                            PartidaObra.obra_id == obra_id
                        )
                    )
                )
            )
        )
    ).all()
    return {fila[0]: fila[1] for fila in filas}


async def _con_desglose(session: AsyncSession, obra_id: uuid.UUID) -> set[uuid.UUID]:
    """Qué partidas tienen parciales. La rejilla lo necesita para no dejar
    teclear a mano una medición que sale de una suma."""
    filas = (
        await session.execute(
            select(MedicionObra.partida_id)
            .join(PartidaObra, PartidaObra.id == MedicionObra.partida_id)
            .where(PartidaObra.obra_id == obra_id)
            .group_by(MedicionObra.partida_id)
        )
    ).all()
    return {fila[0] for fila in filas}


def _partida_out(
    partida: PartidaObra,
    codigos: dict[uuid.UUID, str],
    con_desglose: set[uuid.UUID],
) -> PartidaObraOut:
    salida = PartidaObraOut.model_validate(partida)
    salida.origen_codigo = (
        codigos.get(partida.origen_presupuesto_id)
        if partida.origen_presupuesto_id
        else None
    )
    salida.tiene_desglose = partida.id in con_desglose
    return salida


def _nodo_out(
    nodo: arbol_service.NodoArbol,
    codigos: dict[uuid.UUID, str],
    con_desglose: set[uuid.UUID],
) -> NodoObraOut:
    # OJO: no se valida `nodo.capitulo` directamente contra `NodoObraOut`.
    # `CapituloObra` tiene una relación de verdad llamada `partidas`, y
    # pydantic con `from_attributes` la lee vía `getattr` para rellenar el
    # campo del mismo nombre ANTES de que la línea de abajo la sobrescriba —
    # como no está cargada (aquí se arma a mano desde `arbol_de_obra`), eso
    # dispara un `MissingGreenlet` fuera del `await`. Se valida primero contra
    # el esquema base, que no tiene ese campo, y se construye el nodo aparte.
    base = CapituloObraOut.model_validate(nodo.capitulo)
    return NodoObraOut(
        **base.model_dump(exclude={"origen_codigo"}),
        origen_codigo=(
            codigos.get(nodo.capitulo.origen_presupuesto_id)
            if nodo.capitulo.origen_presupuesto_id
            else None
        ),
        importe=nodo.importe,
        importe_venta=nodo.importe_venta,
        partidas=[_partida_out(p, codigos, con_desglose) for p in nodo.partidas],
        hijos=[_nodo_out(h, codigos, con_desglose) for h in nodo.hijos],
    )


@arbol_router.get("/{obra_id}/arbol", response_model=ArbolObraOut)
async def leer_arbol(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> ArbolObraOut:
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")

    raices = await arbol_service.arbol_de_obra(session, obra_id)
    codigos = await _codigos_de_origen(session, obra_id)
    con_desglose = await _con_desglose(session, obra_id)

    # Los totales se suman sobre las partidas, no sobre los acumulados de los
    # capítulos raíz: así el número sale bien aunque alguna partida quedara
    # colgada de un capítulo que no llega a la raíz.
    filas = (
        await session.execute(
            select(
                func.coalesce(func.sum(PartidaObra.importe), 0),
                func.coalesce(func.sum(PartidaObra.importe_venta), 0),
                func.coalesce(
                    func.sum(PartidaObra.importe).filter(PartidaObra.es_anexo), 0
                ),
                func.coalesce(
                    func.sum(PartidaObra.importe_venta).filter(PartidaObra.es_anexo), 0
                ),
            ).where(PartidaObra.obra_id == obra_id)
        )
    ).one()

    return ArbolObraOut(
        obra_id=obra_id,
        capitulos=[_nodo_out(r, codigos, con_desglose) for r in raices],
        totales=TotalesObraOut(
            coste=Decimal(filas[0]),
            venta=Decimal(filas[1]),
            coste_anexos=Decimal(filas[2]),
            venta_anexos=Decimal(filas[3]),
        ),
    )


class SincronizadoOut(BaseModel):
    """Lo que se ha traído. Los tres a cero significa que ya estaba todo."""

    capitulos: int
    partidas: int
    mediciones: int
    presupuestos: int


@arbol_router.post("/{obra_id}/arbol/sincronizar", response_model=SincronizadoOut)
async def sincronizar_arbol(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> SincronizadoOut:
    """Trae al árbol las partidas de los presupuestos vinculados que aún no se
    hayan copiado.

    Hace falta para las obras que existían antes de que hubiera árbol: la
    migración no las rellenó, porque decidir por el usuario qué presupuesto
    manda y duplicarle mediciones a ciegas es peor que dejarlo vacío y poner un
    botón. Es idempotente: lo ya copiado no se vuelve a copiar.
    """
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")

    total = arbol_service.ResumenCopia()
    presupuestos = 0
    for vinculo in await service.presupuestos_de_obra(session, obra_id):
        parcial = await arbol_service.copiar_presupuesto(
            session,
            obra,
            vinculo.presupuesto_id,
            es_anexo=vinculo.tipo == TipoVinculo.ANEXO,
        )
        if parcial.capitulos or parcial.partidas:
            presupuestos += 1
        total.capitulos += parcial.capitulos
        total.partidas += parcial.partidas
        total.mediciones += parcial.mediciones

    salida = SincronizadoOut(
        capitulos=total.capitulos,
        partidas=total.partidas,
        mediciones=total.mediciones,
        presupuestos=presupuestos,
    )
    await session.commit()
    return salida


@arbol_router.post(
    "/{obra_id}/capitulos",
    response_model=CapituloObraOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_capitulo(
    obra_id: uuid.UUID,
    datos: CapituloObraCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> CapituloObraOut:
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    try:
        capitulo = await arbol_service.crear_capitulo(
            session,
            obra,
            resumen=datos.resumen,
            codigo=datos.codigo,
            parent_id=datos.parent_id,
            texto=datos.texto,
            orden=datos.orden,
        )
    except arbol_service.NodoNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    salida = CapituloObraOut.model_validate(capitulo)
    await session.commit()
    return salida


async def _capitulo_o_404(session: AsyncSession, capitulo_id: uuid.UUID) -> CapituloObra:
    capitulo = await arbol_service.obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    return capitulo


async def _partida_o_404(session: AsyncSession, partida_id: uuid.UUID) -> PartidaObra:
    partida = await arbol_service.obtener_partida(session, partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    return partida


@capitulos_router.patch("/{capitulo_id}", response_model=CapituloObraOut)
async def actualizar_capitulo(
    capitulo_id: uuid.UUID,
    datos: CapituloObraUpdate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> CapituloObraOut:
    capitulo = await _capitulo_o_404(session, capitulo_id)
    try:
        actualizado = await arbol_service.actualizar_capitulo(
            session, capitulo, datos.model_dump(exclude_unset=True)
        )
    except arbol_service.NodoNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    salida = CapituloObraOut.model_validate(actualizado)
    await session.commit()
    return salida


@capitulos_router.delete("/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> None:
    capitulo = await _capitulo_o_404(session, capitulo_id)
    await arbol_service.eliminar_capitulo(session, capitulo)
    await session.commit()


@capitulos_router.post(
    "/{capitulo_id}/partidas",
    response_model=PartidaObraOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_partida(
    capitulo_id: uuid.UUID,
    datos: PartidaObraCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> PartidaObraOut:
    capitulo = await _capitulo_o_404(session, capitulo_id)
    partida = await arbol_service.crear_partida(
        session,
        capitulo,
        resumen=datos.resumen,
        codigo=datos.codigo,
        unidad=datos.unidad,
        precio=datos.precio,
        precio_venta=datos.precio_venta,
        medicion=datos.medicion,
        orden=datos.orden,
    )
    salida = PartidaObraOut.model_validate(partida)
    await session.commit()
    return salida


@partidas_router.get("/{partida_id}", response_model=PartidaObraDetalle)
async def leer_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> PartidaObraDetalle:
    partida = await _partida_o_404(session, partida_id)
    lineas = await arbol_service.lineas_de_partida(session, partida_id)
    origen_codigo = None
    if partida.origen_presupuesto_id is not None:
        origen_codigo = await session.scalar(
            select(Presupuesto.codigo).where(
                Presupuesto.id == partida.origen_presupuesto_id
            )
        )
    # Mismo motivo que en `_nodo_out`: `PartidaObra.lineas` es una relación de
    # verdad y no está cargada; validar contra `PartidaObraOut` (sin el campo
    # `lineas`) evita que pydantic la lea con `getattr` y reviente con
    # `MissingGreenlet`.
    base = PartidaObraOut.model_validate(partida)
    salida = PartidaObraDetalle(
        **base.model_dump(exclude={"origen_codigo", "tiene_desglose"}),
        origen_codigo=origen_codigo,
        tiene_desglose=bool(lineas),
        lineas=[MedicionObraOut.model_validate(l) for l in lineas],
    )
    return salida


@partidas_router.patch("/{partida_id}", response_model=PartidaObraOut)
async def actualizar_partida(
    partida_id: uuid.UUID,
    datos: PartidaObraUpdate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> PartidaObraOut:
    partida = await _partida_o_404(session, partida_id)
    try:
        actualizada = await arbol_service.actualizar_partida(
            session, partida, datos.model_dump(exclude_unset=True)
        )
    except arbol_service.NodoNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    salida = PartidaObraOut.model_validate(actualizada)
    await session.commit()
    return salida


@partidas_router.delete("/{partida_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> None:
    partida = await _partida_o_404(session, partida_id)
    await arbol_service.eliminar_partida(session, partida)
    await session.commit()


@partidas_router.post(
    "/{partida_id}/mediciones",
    response_model=MedicionObraOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_medicion(
    partida_id: uuid.UUID,
    datos: MedicionObraCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> MedicionObraOut:
    partida = await _partida_o_404(session, partida_id)
    linea = await arbol_service.crear_medicion(
        session,
        partida,
        comentario=datos.comentario,
        uds=datos.uds,
        longitud=datos.longitud,
        anchura=datos.anchura,
        altura=datos.altura,
    )
    salida = MedicionObraOut.model_validate(linea)
    await session.commit()
    return salida


async def _medicion_o_404(session: AsyncSession, medicion_id: uuid.UUID) -> MedicionObra:
    linea = await arbol_service.obtener_medicion(session, medicion_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medición no encontrada")
    return linea


@mediciones_router.patch("/{medicion_id}", response_model=MedicionObraOut)
async def actualizar_medicion(
    medicion_id: uuid.UUID,
    datos: MedicionObraUpdate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> MedicionObraOut:
    linea = await _medicion_o_404(session, medicion_id)
    actualizada = await arbol_service.actualizar_medicion(
        session, linea, datos.model_dump(exclude_unset=True)
    )
    salida = MedicionObraOut.model_validate(actualizada)
    await session.commit()
    return salida


@mediciones_router.delete("/{medicion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_medicion(
    medicion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> None:
    linea = await _medicion_o_404(session, medicion_id)
    await arbol_service.eliminar_medicion(session, linea)
    await session.commit()


router = APIRouter()
router.include_router(arbol_router)
router.include_router(capitulos_router)
router.include_router(partidas_router)
router.include_router(mediciones_router)
