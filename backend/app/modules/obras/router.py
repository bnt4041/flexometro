import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
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
from app.modules.obras import arbol_router, ia_router, service, tarea_router
from app.modules.obras.models import (
    Asignacion,
    EstadoObra,
    Obra,
    ObraPresupuesto,
    TipoVinculo,
)
from app.modules.obras.schemas import (
    AceptadoOut,
    AceptarPresupuestoIn,
    AsignacionCreate,
    AsignacionDetalle,
    AsignacionOut,
    AsignacionUpdate,
    ObraCreate,
    ObraDetalle,
    ObraOut,
    ObraResumen,
    ObraUpdate,
    ParteTrabajoCreate,
    ParteTrabajoOut,
    ParteTrabajoUpdate,
    PersonalCreate,
    PersonalOut,
    PersonalUpdate,
    VincularPresupuestoIn,
    VinculoPresupuestoOut,
)

guard = Depends(require_module("obras"))

obras_router = APIRouter(prefix="/api/obras", tags=["obras"], dependencies=[guard])
personal_router = APIRouter(prefix="/api/personal", tags=["obras"], dependencies=[guard])
asignaciones_router = APIRouter(
    prefix="/api/asignaciones", tags=["obras"], dependencies=[guard]
)
partes_router = APIRouter(prefix="/api/partes-trabajo", tags=["obras"], dependencies=[guard])


# --- Personal ---


@personal_router.get("", response_model=Page[PersonalOut])
async def listar_personal(
    activo: bool | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> Page[PersonalOut]:
    items, total = await service.listar_personal(
        session,
        activo=activo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[PersonalOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset
    )


@personal_router.post("", response_model=PersonalOut, status_code=status.HTTP_201_CREATED)
async def crear_personal(
    datos: PersonalCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "crear")),
) -> PersonalOut:
    try:
        persona = await service.crear_personal(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return PersonalOut.model_validate(persona)


@personal_router.get("/{personal_id}", response_model=PersonalOut)
async def detalle_personal(
    personal_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> PersonalOut:
    persona = await service.obtener_personal(session, personal_id)
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajador no encontrado")
    verificar_propiedad(alcance, principal, persona.creado_por_subject)
    return PersonalOut.model_validate(persona)


@personal_router.patch("/{personal_id}", response_model=PersonalOut)
async def actualizar_personal(
    personal_id: uuid.UUID,
    datos: PersonalUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> PersonalOut:
    existente = await service.obtener_personal(session, personal_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajador no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    persona = await service.actualizar_personal(session, personal_id, datos)
    return PersonalOut.model_validate(persona)


@personal_router.delete("/{personal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_personal(
    personal_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "borrar")),
) -> None:
    existente = await service.obtener_personal(session, personal_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trabajador no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    await service.eliminar_personal(session, personal_id)


# --- Obras ---


async def _pem_de(session: AsyncSession, presupuesto_id: uuid.UUID) -> Decimal:
    from app.modules.presupuestos import presupuesto_calculo as calc

    capitulos, partidas = await calc.cargar_estructura(session, presupuesto_id)
    acumulado = calc.importes_por_capitulo(capitulos, partidas)
    return calc.pem_de(capitulos, acumulado)


@obras_router.get("", response_model=Page[ObraResumen])
async def listar(
    estado: EstadoObra | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> Page[ObraResumen]:
    filas, total = await service.listar_obras(
        session,
        estado=estado.value if estado else None,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    items = [
        ObraResumen(
            **ObraOut.model_validate(obra).model_dump(),
            presupuesto_codigo=pres_codigo,
            presupuesto_nombre=pres_nombre,
            pem=await _pem_de(session, obra.presupuesto_id),
        )
        for obra, pres_codigo, pres_nombre in filas
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@obras_router.post("", response_model=ObraOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: ObraCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "crear")),
) -> ObraOut:
    try:
        obra = await service.crear_obra(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ObraOut.model_validate(obra)


def _detalle_asignacion(asignacion: Asignacion, nombre: str, categoria: str | None) -> AsignacionDetalle:
    horas = sum((p.horas for p in asignacion.partes), Decimal("0"))
    coste = sum((p.coste for p in asignacion.partes), Decimal("0.00"))
    return AsignacionDetalle(
        **AsignacionOut.model_validate(asignacion).model_dump(),
        personal_nombre=nombre,
        personal_categoria=categoria,
        partes=[ParteTrabajoOut.model_validate(p) for p in asignacion.partes],
        horas_totales=horas,
        coste_total=coste,
    )


@obras_router.get("/{obra_id}", response_model=ObraDetalle)
async def detalle(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> ObraDetalle:
    resultado = await service.obtener_obra_con_presupuesto(session, obra_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    obra, pres_codigo, pres_nombre = resultado
    verificar_propiedad(alcance, principal, obra.creado_por_subject)

    asignaciones = await service.listar_asignaciones(session, obra_id)
    return ObraDetalle(
        **ObraOut.model_validate(obra).model_dump(),
        presupuesto_codigo=pres_codigo,
        presupuesto_nombre=pres_nombre,
        asignaciones=[
            AsignacionOut.model_validate(a["asignacion"]) for a in asignaciones
        ],
    )


@obras_router.get("/{obra_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> list[RegistroAuditoriaOut]:
    resultado = await service.obtener_obra_con_presupuesto(session, obra_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    obra, _pres_codigo, _pres_nombre = resultado
    verificar_propiedad(alcance, principal, obra.creado_por_subject)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Obra), registro_id=obra_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


async def _obra_propia(
    session: AsyncSession, obra_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    verificar_propiedad(alcance, principal, obra.creado_por_subject)
    return obra


@obras_router.patch("/{obra_id}", response_model=ObraOut)
async def actualizar(
    obra_id: uuid.UUID,
    datos: ObraUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> ObraOut:
    await _obra_propia(session, obra_id, alcance, principal)
    obra = await service.actualizar_obra(session, obra_id, datos)
    return ObraOut.model_validate(obra)


@obras_router.delete("/{obra_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "borrar")),
) -> None:
    await _obra_propia(session, obra_id, alcance, principal)
    await service.eliminar_obra(session, obra_id)


@obras_router.get("/{obra_id}/asignaciones", response_model=list[AsignacionDetalle])
async def listar_asignaciones(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> list[AsignacionDetalle]:
    await _obra_propia(session, obra_id, alcance, principal)
    filas = await service.listar_asignaciones(session, obra_id)
    detalles = []
    for fila in filas:
        completa = await service.obtener_asignacion(session, fila["asignacion"].id)
        detalles.append(
            _detalle_asignacion(completa, fila["personal_nombre"], fila["personal_categoria"])
        )
    return detalles


@obras_router.post(
    "/{obra_id}/asignaciones",
    response_model=AsignacionOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_asignacion(
    obra_id: uuid.UUID,
    datos: AsignacionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "crear")),
) -> AsignacionOut:
    await _obra_propia(session, obra_id, alcance, principal)
    try:
        asignacion = await service.crear_asignacion(session, obra_id, datos)
    except service.PersonalInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert asignacion is not None
    return AsignacionOut.model_validate(asignacion)


async def _asignacion_propia(
    session: AsyncSession, asignacion_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    asignacion = await service.obtener_asignacion(session, asignacion_id)
    if asignacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asignación no encontrada")
    obra = await service.obtener_obra(session, asignacion.obra_id)
    verificar_propiedad(alcance, principal, obra.creado_por_subject if obra else None)
    return asignacion


@asignaciones_router.get("/{asignacion_id}", response_model=AsignacionDetalle)
async def detalle_asignacion(
    asignacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> AsignacionDetalle:
    asignacion = await _asignacion_propia(session, asignacion_id, alcance, principal)
    persona = await service.obtener_personal(session, asignacion.personal_id)
    return _detalle_asignacion(
        asignacion, f"{persona.nombre} {persona.apellidos or ''}".strip(), persona.categoria
    )


@asignaciones_router.patch("/{asignacion_id}", response_model=AsignacionOut)
async def actualizar_asignacion(
    asignacion_id: uuid.UUID,
    datos: AsignacionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> AsignacionOut:
    await _asignacion_propia(session, asignacion_id, alcance, principal)
    asignacion = await service.actualizar_asignacion(session, asignacion_id, datos)
    assert asignacion is not None
    return AsignacionOut.model_validate(asignacion)


@asignaciones_router.delete("/{asignacion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_asignacion(
    asignacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "borrar")),
) -> None:
    await _asignacion_propia(session, asignacion_id, alcance, principal)
    await service.eliminar_asignacion(session, asignacion_id)


@asignaciones_router.post(
    "/{asignacion_id}/partes",
    response_model=ParteTrabajoOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_parte(
    asignacion_id: uuid.UUID,
    datos: ParteTrabajoCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "crear")),
) -> ParteTrabajoOut:
    await _asignacion_propia(session, asignacion_id, alcance, principal)
    try:
        parte = await service.crear_parte(session, asignacion_id, datos)
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert parte is not None
    return ParteTrabajoOut.model_validate(parte)


async def _parte_propio(
    session: AsyncSession, parte_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    parte = await service.obtener_parte(session, parte_id)
    if parte is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parte no encontrado")
    obra = await service.obtener_obra(session, parte.asignacion.obra_id)
    verificar_propiedad(alcance, principal, obra.creado_por_subject if obra else None)
    return parte


@partes_router.patch("/{parte_id}", response_model=ParteTrabajoOut)
async def actualizar_parte(
    parte_id: uuid.UUID,
    datos: ParteTrabajoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> ParteTrabajoOut:
    await _parte_propio(session, parte_id, alcance, principal)
    try:
        parte = await service.actualizar_parte(session, parte_id, datos)
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert parte is not None
    return ParteTrabajoOut.model_validate(parte)


@partes_router.delete("/{parte_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_parte(
    parte_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("obras", "borrar")),
) -> None:
    await _parte_propio(session, parte_id, alcance, principal)
    await service.eliminar_parte(session, parte_id)


# --- Presupuestos en ejecución dentro de la obra ---


async def _vinculos_out(session: AsyncSession, obra_id: uuid.UUID) -> list[VinculoPresupuestoOut]:
    """Los presupuestos de la obra, con su código y nombre resueltos de una vez
    en vez de una consulta por fila."""
    from app.modules.presupuestos.models_presupuesto import Presupuesto

    filas = (
        await session.execute(
            select(ObraPresupuesto, Presupuesto.codigo, Presupuesto.nombre)
            .join(Presupuesto, Presupuesto.id == ObraPresupuesto.presupuesto_id)
            .where(ObraPresupuesto.obra_id == obra_id)
            .order_by(ObraPresupuesto.orden)
        )
    ).all()
    return [
        VinculoPresupuestoOut(
            **VinculoPresupuestoOut.model_validate(v).model_dump(
                exclude={"presupuesto_codigo", "presupuesto_nombre"}
            ),
            presupuesto_codigo=codigo,
            presupuesto_nombre=nombre,
        )
        for v, codigo, nombre in filas
    ]


@obras_router.get("/{obra_id}/presupuestos", response_model=list[VinculoPresupuestoOut])
async def listar_presupuestos_de_obra(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "ver")),
) -> list[VinculoPresupuestoOut]:
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    return await _vinculos_out(session, obra_id)


@obras_router.post("/{obra_id}/presupuestos", response_model=list[VinculoPresupuestoOut])
async def vincular_presupuesto_a_obra(
    obra_id: uuid.UUID,
    datos: VincularPresupuestoIn,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> list[VinculoPresupuestoOut]:
    """Pone otro presupuesto en ejecución en esta obra (un anexo o adenda).
    Lo marca como aprobado, que es lo que significa aceptarlo."""
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    try:
        await service.vincular_presupuesto(
            session, obra, datos.presupuesto_id, tipo=datos.tipo, notas=datos.notas
        )
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    salida = await _vinculos_out(session, obra_id)
    await session.commit()
    return salida


@obras_router.delete(
    "/{obra_id}/presupuestos/{vinculo_id}", response_model=list[VinculoPresupuestoOut]
)
async def desvincular_presupuesto_de_obra(
    obra_id: uuid.UUID,
    vinculo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "borrar")),
) -> list[VinculoPresupuestoOut]:
    vinculo = await session.scalar(
        select(ObraPresupuesto).where(
            ObraPresupuesto.id == vinculo_id, ObraPresupuesto.obra_id == obra_id
        )
    )
    if vinculo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vínculo no encontrado")
    try:
        await service.desvincular_presupuesto(session, vinculo)
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    salida = await _vinculos_out(session, obra_id)
    await session.commit()
    return salida


# --- Aceptar un presupuesto ---
#
# La URL habla de presupuestos pero el router es de `obras`, a propósito:
# `obras` depende de `presupuestos` y no al revés, así que el módulo que puede
# ver los dos es este. Mismo criterio que `compras/costes.py`, que expone
# `/api/obras/{id}/costes` desde `compras`.
aceptar_router = APIRouter(prefix="/api/presupuestos", tags=["obras"], dependencies=[guard])


@aceptar_router.post("/{presupuesto_id}/aceptar", response_model=AceptadoOut)
async def aceptar_presupuesto(
    presupuesto_id: uuid.UUID,
    datos: AceptarPresupuestoIn,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> AceptadoOut:
    """Aceptar un presupuesto es ponerlo en ejecución: o arranca una obra
    nueva, o entra como anexo en una que ya existe. En ambos casos el
    presupuesto queda aprobado y con los precios congelados."""
    try:
        if datos.obra_id is not None:
            obra = await service.obtener_obra(session, datos.obra_id)
            if obra is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada"
                )
            await service.vincular_presupuesto(
                session, obra, presupuesto_id, tipo=TipoVinculo.ANEXO
            )
            creada = False
            tipo = TipoVinculo.ANEXO
        else:
            assert datos.obra_nombre is not None  # lo garantiza el validador del schema
            obra = await service.crear_obra(
                session,
                ObraCreate(
                    nombre=datos.obra_nombre,
                    codigo=datos.obra_codigo,
                    presupuesto_id=presupuesto_id,
                ),
            )
            creada = True
            tipo = TipoVinculo.PRINCIPAL
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    resultado = AceptadoOut(
        obra_id=obra.id,
        obra_codigo=obra.codigo,
        obra_nombre=obra.nombre,
        tipo=tipo,
        creada=creada,
        mensaje=(
            f"Obra «{obra.nombre}» creada y presupuesto aprobado."
            if creada
            else f"Añadido como anexo a «{obra.nombre}», y presupuesto aprobado."
        ),
    )
    await session.commit()
    return resultado


router = APIRouter()
router.include_router(obras_router)
# El árbol de la obra vive en su propio módulo: son muchas rutas y no tienen
# nada que ver con la ficha.
router.include_router(arbol_router.router)
router.include_router(ia_router.ia_router)
router.include_router(tarea_router.router)
router.include_router(aceptar_router)
router.include_router(personal_router)
router.include_router(asignaciones_router)
router.include_router(partes_router)
