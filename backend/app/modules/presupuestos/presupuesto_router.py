import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.presupuestos import informes
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos import presupuesto_service as service
from app.modules.presupuestos import versionado
from app.modules.presupuestos.models_presupuesto import EstadoPresupuesto
from app.modules.presupuestos.presupuesto_schemas import (
    CambioOut,
    CapituloCreate,
    CapituloUpdate,
    ComparacionOut,
    GuardarComoPlantilla,
    InstanciarPlantilla,
    LineaMedicionCreate,
    LineaMedicionOut,
    LineaMedicionUpdate,
    PartidaCreate,
    PartidaDetalle,
    PartidaOut,
    PartidaUpdate,
    PresupuestoCreate,
    PresupuestoDetalle,
    PresupuestoOut,
    PresupuestoResumen,
    PresupuestoUpdate,
    ResultadoSincronizacion,
    VersionOut,
)

guard = Depends(require_module("presupuestos"))

presupuestos_router = APIRouter(
    prefix="/api/presupuestos", tags=["presupuestos"], dependencies=[guard]
)
capitulos_router = APIRouter(prefix="/api/capitulos", tags=["presupuestos"], dependencies=[guard])
partidas_router = APIRouter(prefix="/api/partidas", tags=["presupuestos"], dependencies=[guard])
mediciones_router = APIRouter(
    prefix="/api/mediciones", tags=["presupuestos"], dependencies=[guard]
)


@presupuestos_router.get("", response_model=Page[PresupuestoResumen])
async def listar(
    q: str | None = None,
    estado: EstadoPresupuesto | None = None,
    es_plantilla: bool = Query(default=False, description="true para listar plantillas"),
    solo_ultima_version: bool = Query(
        default=False, description="Solo la versión más alta de cada línea"
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> Page[PresupuestoResumen]:
    items, total = await service.listar(
        session,
        q=q,
        estado=estado.value if estado else None,
        es_plantilla=es_plantilla,
        solo_ultima_version=solo_ultima_version,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    filas = []
    for presupuesto in items:
        pem, importe = await service.total_de(session, presupuesto)
        filas.append(
            PresupuestoResumen(
                **PresupuestoOut.model_validate(presupuesto).model_dump(),
                pem=pem,
                total=importe,
            )
        )
    return Page(items=filas, total=total, limit=limit, offset=offset)


@presupuestos_router.post("", response_model=PresupuestoOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: PresupuestoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    try:
        presupuesto = await service.crear(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PresupuestoOut.model_validate(presupuesto)


async def _presupuesto_propio(
    session: AsyncSession, presupuesto_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    presupuesto = await service.obtener(session, presupuesto_id)
    if presupuesto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado"
        )
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject)
    return presupuesto


@presupuestos_router.get("/{presupuesto_id}", response_model=PresupuestoDetalle)
async def detalle(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> PresupuestoDetalle:
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    capitulos, totales = await service.arbol_y_totales(session, presupuesto)
    desfasadas = await calc.partidas_desactualizadas(session, presupuesto_id)
    return PresupuestoDetalle(
        **PresupuestoOut.model_validate(presupuesto).model_dump(),
        capitulos=capitulos,
        totales=totales,
        partidas_desactualizadas=len(desfasadas),
    )


@presupuestos_router.patch("/{presupuesto_id}", response_model=PresupuestoOut)
async def actualizar(
    presupuesto_id: uuid.UUID,
    datos: PresupuestoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    presupuesto = await service.actualizar(session, presupuesto_id, datos)
    return PresupuestoOut.model_validate(presupuesto)


@presupuestos_router.delete("/{presupuesto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    await service.eliminar(session, presupuesto_id)


@presupuestos_router.post(
    "/{presupuesto_id}/sincronizar-precios", response_model=ResultadoSincronizacion
)
async def sincronizar_precios(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoSincronizacion:
    """Trae los precios actuales del cuadro, incluso con los precios
    bloqueados. Es una acción deliberada, nunca automática."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    return ResultadoSincronizacion(
        partidas_actualizadas=await calc.sincronizar_precios(session, presupuesto_id)
    )


@presupuestos_router.post(
    "/{presupuesto_id}/capitulos", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def crear_capitulo(
    presupuesto_id: uuid.UUID,
    datos: CapituloCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    capitulo = await service.crear_capitulo(session, presupuesto_id, datos)
    assert capitulo is not None
    return {
        "id": str(capitulo.id),
        "codigo": capitulo.codigo,
        "resumen": capitulo.resumen,
        "parent_id": str(capitulo.parent_id) if capitulo.parent_id else None,
    }


async def _capitulo_propio(
    session: AsyncSession, capitulo_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    capitulo = await service.obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    presupuesto = await service.obtener(session, capitulo.presupuesto_id)
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject if presupuesto else None)
    return capitulo


@capitulos_router.patch("/{capitulo_id}", response_model=dict)
async def actualizar_capitulo(
    capitulo_id: uuid.UUID,
    datos: CapituloUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    capitulo = await service.actualizar_capitulo(session, capitulo_id, datos)
    assert capitulo is not None
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@capitulos_router.delete("/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    await service.eliminar_capitulo(session, capitulo_id)


@capitulos_router.post(
    "/{capitulo_id}/partidas", response_model=PartidaOut, status_code=status.HTTP_201_CREATED
)
async def crear_partida(
    capitulo_id: uuid.UUID,
    datos: PartidaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PartidaOut:
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
    return PartidaOut.model_validate(partida)


async def _partida_propia(
    session: AsyncSession, partida_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    partida = await service.obtener_partida(session, partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    presupuesto = await service.obtener(session, partida.presupuesto_id)
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject if presupuesto else None)
    return partida


@partidas_router.get("/{partida_id}", response_model=PartidaDetalle)
async def detalle_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> PartidaDetalle:
    partida = await _partida_propia(session, partida_id, alcance, principal)

    detalle = PartidaDetalle(
        **PartidaOut.model_validate(partida).model_dump(),
        lineas=[LineaMedicionOut.model_validate(l) for l in partida.lineas],
    )
    # Se informa el precio del cuadro solo cuando difiere: es la señal de que
    # el presupuesto está bloqueado y el cuadro se ha movido por debajo.
    if partida.concepto_id is not None:
        from app.modules.presupuestos.service import obtener_concepto

        concepto = await obtener_concepto(session, partida.concepto_id)
        if concepto is not None and concepto.precio != partida.precio:
            detalle.precio_cuadro = concepto.precio
    return detalle


@partidas_router.patch("/{partida_id}", response_model=PartidaOut)
async def actualizar_partida(
    partida_id: uuid.UUID,
    datos: PartidaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    partida = await service.actualizar_partida(session, partida_id, datos)
    assert partida is not None
    return PartidaOut.model_validate(partida)


@partidas_router.delete("/{partida_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _partida_propia(session, partida_id, alcance, principal)
    await service.eliminar_partida(session, partida_id)


@partidas_router.post("/{partida_id}/integrar-banco-precios", response_model=PartidaOut)
async def integrar_en_banco_precios(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        partida = await service.integrar_en_banco_precios(session, partida_id)
    except (service.ConceptoYaVinculado, service.CodigoDuplicado) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    assert partida is not None
    return PartidaOut.model_validate(partida)


@partidas_router.post(
    "/{partida_id}/lineas", response_model=LineaMedicionOut, status_code=status.HTTP_201_CREATED
)
async def crear_linea(
    partida_id: uuid.UUID,
    datos: LineaMedicionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> LineaMedicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    linea = await service.crear_linea(session, partida_id, datos)
    assert linea is not None
    return LineaMedicionOut.model_validate(linea)


async def _linea_medicion_propia(
    session: AsyncSession, linea_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    linea = await service.obtener_linea(session, linea_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    await _partida_propia(session, linea.partida_id, alcance, principal)
    return linea


@mediciones_router.patch("/{linea_id}", response_model=LineaMedicionOut)
async def actualizar_linea(
    linea_id: uuid.UUID,
    datos: LineaMedicionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> LineaMedicionOut:
    await _linea_medicion_propia(session, linea_id, alcance, principal)
    linea = await service.actualizar_linea(session, linea_id, datos)
    assert linea is not None
    return LineaMedicionOut.model_validate(linea)


@mediciones_router.delete("/{linea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_linea(
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _linea_medicion_propia(session, linea_id, alcance, principal)
    await service.eliminar_linea(session, linea_id)


# --- Versiones, plantillas e informes ---


@presupuestos_router.get("/{presupuesto_id}/versiones", response_model=list[VersionOut])
async def versiones(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[VersionOut]:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        filas = await versionado.versiones_de(session, presupuesto_id)
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [VersionOut.model_validate(v) for v in filas]


@presupuestos_router.post(
    "/{presupuesto_id}/nueva-version",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def nueva_version(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    """Duplica el presupuesto como versión siguiente, en borrador y con los
    precios sueltos otra vez."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        nueva = await versionado.nueva_version(session, presupuesto_id)
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PresupuestoOut.model_validate(nueva)


@presupuestos_router.get("/{a_id}/comparar/{b_id}", response_model=ComparacionOut)
async def comparar(
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> ComparacionOut:
    await _presupuesto_propio(session, a_id, alcance, principal)
    await _presupuesto_propio(session, b_id, alcance, principal)
    try:
        resultado = await versionado.comparar(session, a_id, b_id)
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    a = await service.obtener(session, a_id)
    b = await service.obtener(session, b_id)
    _, total_a = await service.total_de(session, a)
    _, total_b = await service.total_de(session, b)

    def convertir(cambios) -> list[CambioOut]:
        return [
            CambioOut(
                codigo=c.codigo,
                resumen=c.resumen,
                unidad=c.unidad,
                medicion_a=c.medicion_a,
                medicion_b=c.medicion_b,
                precio_a=c.precio_a,
                precio_b=c.precio_b,
                importe_a=c.importe_a,
                importe_b=c.importe_b,
                delta=c.delta,
            )
            for c in cambios
        ]

    return ComparacionOut(
        a=VersionOut.model_validate(a),
        b=VersionOut.model_validate(b),
        total_a=total_a,
        total_b=total_b,
        delta_total=total_b - total_a,
        altas=convertir(resultado.altas),
        bajas=convertir(resultado.bajas),
        cambios=convertir(resultado.cambios),
        sin_cambios=resultado.sin_cambios,
    )


@presupuestos_router.post(
    "/{presupuesto_id}/guardar-como-plantilla",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def guardar_como_plantilla(
    presupuesto_id: uuid.UUID,
    datos: GuardarComoPlantilla,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        plantilla = await versionado.guardar_como_plantilla(
            session,
            presupuesto_id,
            nombre=datos.nombre,
            codigo=datos.codigo or await service.siguiente_codigo(session),
            tipo_obra=datos.tipo_obra,
            con_mediciones=datos.con_mediciones,
        )
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PresupuestoOut.model_validate(plantilla)


@presupuestos_router.post(
    "/{plantilla_id}/instanciar",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def instanciar(
    plantilla_id: uuid.UUID,
    datos: InstanciarPlantilla,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    """Crea un presupuesto nuevo con la estructura de la plantilla.

    No se comprueba la propiedad de la plantilla de origen: las plantillas son
    un recurso compartido dentro de la organización, no algo que "propios"
    deba restringir — lo que sí es propio es el presupuesto nuevo que resulta,
    y ese ya nace con la autoría de quien lo instancia.
    """
    try:
        nuevo = await versionado.instanciar_plantilla(
            session,
            plantilla_id,
            nombre=datos.nombre,
            codigo=datos.codigo or await service.siguiente_codigo(session),
            cliente_id=datos.cliente_id,
            emplazamiento=datos.emplazamiento,
        )
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PresupuestoOut.model_validate(nuevo)


@presupuestos_router.get("/{presupuesto_id}/pdf/{documento}")
async def descargar_pdf(
    presupuesto_id: uuid.UUID,
    documento: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> Response:
    """Presupuesto, estado de mediciones o cuadro de precios descompuestos."""
    if documento not in informes.DOCUMENTOS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento desconocido. Disponibles: {', '.join(informes.DOCUMENTOS)}",
        )
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)

    pdf = await informes.generar(session, presupuesto, documento)
    nombre = f"{presupuesto.codigo}-{documento}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


router = APIRouter()
router.include_router(presupuestos_router)
router.include_router(capitulos_router)
router.include_router(partidas_router)
router.include_router(mediciones_router)
