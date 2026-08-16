import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.compras import costes, service
from app.modules.compras.schemas import (
    AlbaranCreate,
    AlbaranDetalle,
    AlbaranLineaCreate,
    AlbaranLineaOut,
    AlbaranLineaUpdate,
    AlbaranOut,
    AlbaranResumen,
    AlbaranUpdate,
    InformeCosteObra,
)

guard = Depends(require_module("compras"))

albaranes_router = APIRouter(prefix="/api/albaranes", tags=["compras"], dependencies=[guard])
lineas_router = APIRouter(
    prefix="/api/albaranes-lineas", tags=["compras"], dependencies=[guard]
)
# Prefijo /api/obras a propósito: el informe cruza datos de obras + compras +
# presupuestos, y compras es el único módulo con permiso para conocer los
# tres (ver costes.py). El router vive aquí; la URL habla de "obras" porque es
# lo que el usuario está consultando.
costes_router = APIRouter(prefix="/api/obras", tags=["compras"], dependencies=[guard])


@albaranes_router.get("", response_model=Page[AlbaranResumen])
async def listar(
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> Page[AlbaranResumen]:
    filas, total = await service.listar_albaranes(
        session,
        obra_id=obra_id,
        proveedor_id=proveedor_id,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    totales = await service.totales_de_albaranes(session, [a.id for a, _ in filas])
    items = [
        AlbaranResumen(
            **AlbaranOut.model_validate(albaran).model_dump(),
            proveedor_razon_social=razon_social,
            total=totales.get(albaran.id, Decimal("0.00")),
        )
        for albaran, razon_social in filas
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@albaranes_router.post("", response_model=AlbaranDetalle, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: AlbaranCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranDetalle:
    try:
        albaran = await service.crear_albaran(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        service.ObraInvalida,
        service.ProveedorInvalido,
        service.ProductoInvalido,
        service.LineaSinDatos,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    resultado = await service.obtener_albaran(session, albaran.id)
    albaran, razon_social = resultado
    return AlbaranDetalle(
        **AlbaranOut.model_validate(albaran).model_dump(),
        proveedor_razon_social=razon_social,
        lineas=[AlbaranLineaOut.model_validate(l) for l in albaran.lineas],
        total=service.total_de(albaran.lineas),
    )


async def _albaran_propio(
    session: AsyncSession, albaran_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    resultado = await service.obtener_albaran(session, albaran_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Albarán no encontrado")
    albaran, razon_social = resultado
    verificar_propiedad(alcance, principal, albaran.creado_por_subject)
    return albaran, razon_social


@albaranes_router.get("/{albaran_id}", response_model=AlbaranDetalle)
async def detalle(
    albaran_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> AlbaranDetalle:
    albaran, razon_social = await _albaran_propio(session, albaran_id, alcance, principal)
    return AlbaranDetalle(
        **AlbaranOut.model_validate(albaran).model_dump(),
        proveedor_razon_social=razon_social,
        lineas=[AlbaranLineaOut.model_validate(l) for l in albaran.lineas],
        total=service.total_de(albaran.lineas),
    )


@albaranes_router.patch("/{albaran_id}", response_model=AlbaranOut)
async def actualizar(
    albaran_id: uuid.UUID,
    datos: AlbaranUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranOut:
    await _albaran_propio(session, albaran_id, alcance, principal)
    albaran = await service.actualizar_albaran(session, albaran_id, datos)
    return AlbaranOut.model_validate(albaran)


@albaranes_router.delete("/{albaran_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    albaran_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _albaran_propio(session, albaran_id, alcance, principal)
    await service.eliminar_albaran(session, albaran_id)


@albaranes_router.post(
    "/{albaran_id}/lineas", response_model=AlbaranLineaOut, status_code=status.HTTP_201_CREATED
)
async def anadir_linea(
    albaran_id: uuid.UUID,
    datos: AlbaranLineaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranLineaOut:
    await _albaran_propio(session, albaran_id, alcance, principal)
    try:
        linea = await service.anadir_linea(session, albaran_id, datos)
    except (service.ProductoInvalido, service.LineaSinDatos) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert linea is not None
    return AlbaranLineaOut.model_validate(linea)


async def _linea_propia(
    session: AsyncSession, linea_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    linea = await service.obtener_linea(session, linea_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    await _albaran_propio(session, linea.albaran_id, alcance, principal)
    return linea


@lineas_router.patch("/{linea_id}", response_model=AlbaranLineaOut)
async def actualizar_linea(
    linea_id: uuid.UUID,
    datos: AlbaranLineaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> AlbaranLineaOut:
    await _linea_propia(session, linea_id, alcance, principal)
    linea = await service.actualizar_linea(session, linea_id, datos)
    assert linea is not None
    return AlbaranLineaOut.model_validate(linea)


@lineas_router.delete("/{linea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_linea(
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> None:
    await _linea_propia(session, linea_id, alcance, principal)
    await service.eliminar_linea(session, linea_id)


@costes_router.get("/{obra_id}/costes", response_model=InformeCosteObra)
async def coste_real_vs_presupuestado(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> InformeCosteObra:
    from app.modules.obras.service import obtener_obra

    obra = await obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    verificar_propiedad(alcance, principal, obra.creado_por_subject)
    informe = await costes.informe_coste(session, obra_id)
    assert informe is not None
    return informe


router = APIRouter()
router.include_router(albaranes_router)
router.include_router(lineas_router)
router.include_router(costes_router)
