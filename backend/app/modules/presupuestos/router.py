import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut
from app.modules.presupuestos import banco_service, calculo, service
from app.modules.presupuestos.models import Concepto, TipoConcepto
from app.modules.presupuestos.schemas import (
    ArbolBanco,
    AsignarFamiliaIn,
    CapituloBancoCreate,
    CapituloBancoOut,
    CapituloBancoUpdate,
    ConceptoCreate,
    ConceptoDetalle,
    ConceptoOut,
    ConceptoUpdate,
    FamiliaCreate,
    FamiliaOut,
    FamiliaUpdate,
    HistoricoPrecioOut,
    LineaCreate,
    LineaOut,
    LineaUpdate,
    MoverAlCapituloIn,
    MoverPorNaturalezaIn,
    NodoArbol,
    PaginaFichas,
    PrecioSuministroCreate,
    PrecioSuministroOut,
    PrecioSuministroUpdate,
    ResultadoRecalculo,
    UsoCompletoOut,
)

guard = Depends(require_module("presupuestos"))

conceptos_router = APIRouter(prefix="/api/conceptos", tags=["presupuestos"], dependencies=[guard])
lineas_router = APIRouter(
    prefix="/api/descomposicion", tags=["presupuestos"], dependencies=[guard]
)
familias_router = APIRouter(prefix="/api/familias", tags=["presupuestos"], dependencies=[guard])
banco_router = APIRouter(prefix="/api/banco", tags=["presupuestos"], dependencies=[guard])
suministros_router = APIRouter(
    prefix="/api/suministros", tags=["presupuestos"], dependencies=[guard]
)


def _detalle(concepto) -> ConceptoDetalle:
    """Detalle a partir de la proyección, no del objeto ORM.

    `ConceptoDetalle.lineas` son `LineaOut` con los datos del hijo ya resueltos;
    validar directamente contra el ORM intentaría leerlas de las
    `Descomposicion` crudas, que no tienen esos campos.
    """
    lineas = service.lineas_de(concepto)
    return ConceptoDetalle(
        **ConceptoOut.model_validate(concepto).model_dump(),
        lineas=lineas,
        coste_directo=service.coste_directo_de(lineas),
        clase=service.clase_de(concepto),
        suministros=[PrecioSuministroOut.model_validate(s) for s in concepto.suministros],
    )


@conceptos_router.get("", response_model=Page[ConceptoOut])
async def listar(
    q: str | None = Query(default=None, description="Busca en resumen, código, texto y EAN"),
    tipo: TipoConcepto | None = None,
    activo: bool | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> Page[ConceptoOut]:
    items, total = await service.listar_conceptos(
        session,
        q=q,
        tipo=tipo.value if tipo else None,
        activo=activo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[ConceptoOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@conceptos_router.post("", response_model=ConceptoDetalle, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: ConceptoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ConceptoDetalle:
    try:
        concepto = await service.crear_concepto(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _detalle(concepto)


@conceptos_router.get("/{concepto_id}", response_model=ConceptoDetalle)
async def detalle(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> ConceptoDetalle:
    concepto = await service.obtener_concepto_visible(session, concepto_id)
    if concepto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, concepto.creado_por_subject)
    return _detalle(concepto)


@conceptos_router.get("/{concepto_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[RegistroAuditoriaOut]:
    concepto = await service.obtener_concepto_visible(session, concepto_id)
    if concepto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, concepto.creado_por_subject)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Concepto), registro_id=concepto_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@conceptos_router.patch("/{concepto_id}", response_model=ConceptoDetalle)
async def actualizar(
    concepto_id: uuid.UUID,
    datos: ConceptoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ConceptoDetalle:
    existente = await service.obtener_concepto(session, concepto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    concepto = await service.actualizar_concepto(session, concepto_id, datos)
    return _detalle(concepto)


@conceptos_router.delete("/{concepto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    existente = await service.obtener_concepto(session, concepto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    try:
        await service.eliminar_concepto(session, concepto_id)
    except service.ConceptoEnUso as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@conceptos_router.get("/{concepto_id}/arbol", response_model=NodoArbol)
async def arbol(
    concepto_id: uuid.UUID,
    profundidad: int = Query(default=6, ge=1, le=15),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> NodoArbol:
    existente = await service.obtener_concepto_visible(session, concepto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    nodo = await service.arbol(session, concepto_id, profundidad=profundidad)
    assert nodo is not None
    return nodo


@conceptos_router.get("/{concepto_id}/donde-se-usa", response_model=UsoCompletoOut)
async def donde_se_usa(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> UsoCompletoOut:
    existente = await service.obtener_concepto(session, concepto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    return await service.donde_se_usa(session, concepto_id)


@conceptos_router.get("/{concepto_id}/historico-precios", response_model=list[HistoricoPrecioOut])
async def historico_precios(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[HistoricoPrecioOut]:
    existente = await service.obtener_concepto(session, concepto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    return await service.historico_de(session, concepto_id)


@conceptos_router.post("/{concepto_id}/recalcular", response_model=ResultadoRecalculo)
async def recalcular(
    concepto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoRecalculo:
    """Fuerza el recálculo del concepto y de todo lo que depende de él."""
    concepto = await service.obtener_concepto(session, concepto_id)
    if concepto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, concepto.creado_por_subject)
    ids = await calculo.recalcular_cascada(session, concepto_id)
    return ResultadoRecalculo(conceptos_modificados=len(ids), ids=ids)


@conceptos_router.post(
    "/{concepto_id}/lineas", response_model=LineaOut, status_code=status.HTTP_201_CREATED
)
async def anadir_linea(
    concepto_id: uuid.UUID,
    datos: LineaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> LineaOut:
    padre = await service.obtener_concepto(session, concepto_id)
    if padre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, padre.creado_por_subject)
    try:
        linea = await service.anadir_linea(session, concepto_id, datos)
    except calculo.CicloDetectado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.HijoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert linea is not None

    concepto = await service.obtener_concepto(session, concepto_id)
    return next(l for l in service.lineas_de(concepto) if l.id == linea.id)


async def _verificar_propiedad_linea(
    session: AsyncSession, linea_id: uuid.UUID, alcance: Alcance, principal: Principal
) -> None:
    linea = await service.obtener_linea(session, linea_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    padre = await service.obtener_concepto(session, linea.padre_id)
    verificar_propiedad(alcance, principal, padre.creado_por_subject if padre else None)


@lineas_router.patch("/{linea_id}", response_model=LineaOut)
async def actualizar_linea(
    linea_id: uuid.UUID,
    datos: LineaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> LineaOut:
    await _verificar_propiedad_linea(session, linea_id, alcance, principal)
    linea = await service.actualizar_linea(session, linea_id, datos)
    assert linea is not None
    concepto = await service.obtener_concepto(session, linea.padre_id)
    return next(l for l in service.lineas_de(concepto) if l.id == linea_id)


@lineas_router.delete("/{linea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_linea(
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _verificar_propiedad_linea(session, linea_id, alcance, principal)
    await service.eliminar_linea(session, linea_id)


# --- Familias ---


@familias_router.get("", response_model=list[FamiliaOut])
async def listar_familias(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[FamiliaOut]:
    familias = await service.listar_familias(
        session, creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None
    )
    return [FamiliaOut.model_validate(f) for f in familias]


@familias_router.post("", response_model=FamiliaOut, status_code=status.HTTP_201_CREATED)
async def crear_familia(
    datos: FamiliaCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> FamiliaOut:
    try:
        familia = await service.crear_familia(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FamiliaOut.model_validate(familia)


@familias_router.patch("/{familia_id}", response_model=FamiliaOut)
async def actualizar_familia(
    familia_id: uuid.UUID,
    datos: FamiliaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> FamiliaOut:
    existente = await service.obtener_familia(session, familia_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Familia no encontrada")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    familia = await service.actualizar_familia(session, familia_id, datos)
    return FamiliaOut.model_validate(familia)


@familias_router.delete("/{familia_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_familia(
    familia_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    existente = await service.obtener_familia(session, familia_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Familia no encontrada")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    await service.eliminar_familia(session, familia_id)


# --- Precios de suministro ---


@conceptos_router.post(
    "/{concepto_id}/suministros",
    response_model=PrecioSuministroOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_suministro(
    concepto_id: uuid.UUID,
    datos: PrecioSuministroCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PrecioSuministroOut:
    concepto = await service.obtener_concepto(session, concepto_id)
    if concepto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concepto no encontrado")
    verificar_propiedad(alcance, principal, concepto.creado_por_subject)
    try:
        suministro = await service.crear_suministro(session, concepto_id, datos)
    except service.ProveedorInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert suministro is not None
    return PrecioSuministroOut.model_validate(suministro)


async def _verificar_propiedad_suministro(
    session: AsyncSession, suministro_id: uuid.UUID, alcance: Alcance, principal: Principal
) -> None:
    suministro = await service.obtener_suministro(session, suministro_id)
    if suministro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarifa no encontrada")
    concepto = await service.obtener_concepto(session, suministro.concepto_id)
    verificar_propiedad(alcance, principal, concepto.creado_por_subject if concepto else None)


@suministros_router.patch("/{suministro_id}", response_model=PrecioSuministroOut)
async def actualizar_suministro(
    suministro_id: uuid.UUID,
    datos: PrecioSuministroUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PrecioSuministroOut:
    await _verificar_propiedad_suministro(session, suministro_id, alcance, principal)
    try:
        suministro = await service.actualizar_suministro(session, suministro_id, datos)
    except service.ProveedorInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert suministro is not None
    return PrecioSuministroOut.model_validate(suministro)


@suministros_router.delete("/{suministro_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_suministro(
    suministro_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _verificar_propiedad_suministro(session, suministro_id, alcance, principal)
    await service.eliminar_suministro(session, suministro_id)


# --- El banco de precios como árbol (Fase 50) ---
#
# `capitulo_id` = dónde está la ficha (estructura, se arrastra);
# `familia_id` = qué es la ficha (clasificación, se asigna en masa). Ver el
# docstring de `banco_service`.


@banco_router.get("/arbol", response_model=ArbolBanco)
async def arbol_banco(
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> ArbolBanco:
    """Capítulos y fichas de una vez: la rejilla necesita el banco entero
    para poder plegar, filtrar y arrastrar sin ir pidiendo ramas sueltas."""
    return await banco_service.arbol(session)


@banco_router.get("/fichas", response_model=PaginaFichas)
async def fichas_banco(
    capitulo_id: uuid.UUID | None = None,
    sin_capitulo: bool = False,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> PaginaFichas:
    """Las fichas de un capítulo, paginadas. Nunca se devuelve el banco
    entero: uno importado de verdad pasa de las 12.000 fichas."""
    return await banco_service.fichas(
        session,
        capitulo_id=capitulo_id,
        sin_capitulo=sin_capitulo,
        q=q,
        limit=limit,
        offset=offset,
    )


@banco_router.post(
    "/capitulos", response_model=CapituloBancoOut, status_code=status.HTTP_201_CREATED
)
async def crear_capitulo_banco(
    datos: CapituloBancoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> CapituloBancoOut:
    try:
        capitulo = await banco_service.crear_capitulo(session, datos)
    except banco_service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return CapituloBancoOut.model_validate(capitulo)


@banco_router.patch("/capitulos/{capitulo_id}", response_model=CapituloBancoOut)
async def actualizar_capitulo_banco(
    capitulo_id: uuid.UUID,
    datos: CapituloBancoUpdate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> CapituloBancoOut:
    try:
        capitulo = await banco_service.actualizar_capitulo(session, capitulo_id, datos)
    except banco_service.CicloDeCapitulos as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    await session.commit()
    return CapituloBancoOut.model_validate(capitulo)


@banco_router.delete("/capitulos/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo_banco(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    try:
        encontrado = await banco_service.eliminar_capitulo(session, capitulo_id)
    except banco_service.CapituloConContenido as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not encontrado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    await session.commit()


@banco_router.post("/asignar-familia", response_model=dict)
async def asignar_familia(
    datos: AsignarFamiliaIn,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    """Clasificar fichas, una o muchas — la rejilla manda siempre lista."""
    tocadas = await banco_service.asignar_familia(session, datos.concepto_ids, datos.familia_id)
    await session.commit()
    return {"actualizados": tocadas}


@banco_router.post("/mover", response_model=dict)
async def mover_al_capitulo(
    datos: MoverAlCapituloIn,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    try:
        tocadas = await banco_service.mover_al_capitulo(
            session, datos.concepto_ids, datos.capitulo_id
        )
    except banco_service.CapituloConContenido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return {"actualizados": tocadas}


@banco_router.post("/mover-por-naturaleza", response_model=dict)
async def mover_por_naturaleza(
    datos: MoverPorNaturalezaIn,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    """Mueve TODAS las fichas de una naturaleza de una vez — la usa la
    confirmación de "Ayuda con IA" cuando organiza el banco por naturaleza
    (Fase 50), sin depender de una lista de ids."""
    try:
        tocadas = await banco_service.mover_por_naturaleza(
            session, datos.naturaleza.value, datos.capitulo_id
        )
    except banco_service.CapituloConContenido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return {"actualizados": tocadas}


router = APIRouter()
router.include_router(conceptos_router)
router.include_router(lineas_router)
router.include_router(familias_router)
router.include_router(banco_router)
router.include_router(suministros_router)

# El presupuesto vive en su propio fichero: comparte módulo con el banco de
# precios, pero son dos dominios distintos y mezclarlos en un router haría
# ilegibles los dos.
from app.modules.presupuestos.presupuesto_router import router as presupuesto_router  # noqa: E402

router.include_router(presupuesto_router)

from app.modules.presupuestos.fiebdc_router import router as fiebdc_router  # noqa: E402

router.include_router(fiebdc_router)

from app.modules.presupuestos import plantilla_docx_router  # noqa: E402

router.include_router(plantilla_docx_router.router)
router.include_router(plantilla_docx_router.tenant_router)
