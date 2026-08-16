import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance, TipoProducto
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.catalogo import service
from app.modules.catalogo.schemas import (
    FamiliaCreate,
    FamiliaOut,
    FamiliaUpdate,
    PrecioSuministroCreate,
    PrecioSuministroOut,
    PrecioSuministroUpdate,
    ProductoCreate,
    ProductoDetalle,
    ProductoOut,
    ProductoUpdate,
)

guard = Depends(require_module("catalogo"))

productos_router = APIRouter(
    prefix="/api/productos", tags=["catalogo"], dependencies=[guard]
)
familias_router = APIRouter(
    prefix="/api/familias", tags=["catalogo"], dependencies=[guard]
)
suministros_router = APIRouter(
    prefix="/api/suministros", tags=["catalogo"], dependencies=[guard]
)


# --- Familias ---


@familias_router.get("", response_model=list[FamiliaOut])
async def listar_familias(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "ver")),
) -> list[FamiliaOut]:
    familias = await service.listar_familias(
        session, creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None
    )
    return [FamiliaOut.model_validate(f) for f in familias]


@familias_router.post("", response_model=FamiliaOut, status_code=status.HTTP_201_CREATED)
async def crear_familia(
    datos: FamiliaCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
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
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
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
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
) -> None:
    existente = await service.obtener_familia(session, familia_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Familia no encontrada")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    await service.eliminar_familia(session, familia_id)


# --- Productos ---


@productos_router.get("", response_model=Page[ProductoOut])
async def listar(
    q: str | None = Query(default=None, description="Busca en resumen, código, EAN"),
    tipo: TipoProducto | None = None,
    familia_id: uuid.UUID | None = None,
    activo: bool | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "ver")),
) -> Page[ProductoOut]:
    items, total = await service.listar_productos(
        session,
        q=q,
        tipo=tipo.value if tipo else None,
        familia_id=familia_id,
        activo=activo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[ProductoOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@productos_router.post("", response_model=ProductoDetalle, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: ProductoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
) -> ProductoDetalle:
    try:
        producto = await service.crear_producto(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ProductoDetalle.model_validate(producto)


@productos_router.get("/siguiente-codigo", response_model=str)
async def siguiente_codigo(session: AsyncSession = Depends(get_session)) -> str:
    return await service.siguiente_codigo(session)


@productos_router.get("/{producto_id}", response_model=ProductoDetalle)
async def detalle(
    producto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "ver")),
) -> ProductoDetalle:
    producto = await service.obtener_producto_visible(session, producto_id)
    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    verificar_propiedad(alcance, principal, producto.creado_por_subject)
    return ProductoDetalle.model_validate(producto)


@productos_router.patch("/{producto_id}", response_model=ProductoOut)
async def actualizar(
    producto_id: uuid.UUID,
    datos: ProductoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
) -> ProductoOut:
    existente = await service.obtener_producto(session, producto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    producto = await service.actualizar_producto(session, producto_id, datos)
    return ProductoOut.model_validate(producto)


@productos_router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    producto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
) -> None:
    existente = await service.obtener_producto(session, producto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    await service.eliminar_producto(session, producto_id)


@productos_router.post(
    "/{producto_id}/suministros",
    response_model=PrecioSuministroOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_suministro(
    producto_id: uuid.UUID,
    datos: PrecioSuministroCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
) -> PrecioSuministroOut:
    producto = await service.obtener_producto(session, producto_id)
    if producto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    verificar_propiedad(alcance, principal, producto.creado_por_subject)
    try:
        suministro = await service.crear_suministro(session, producto_id, datos)
    except service.ProveedorInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert suministro is not None
    return PrecioSuministroOut.model_validate(suministro)


@productos_router.get("/{producto_id}/precio-referencia", response_model=float | None)
async def precio_referencia(
    producto_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> float | None:
    """Precio que tomará el precio básico en Fase 2: la tarifa preferente, o la
    vigente más reciente."""
    precio = await service.precio_referencia(session, producto_id)
    return float(precio) if precio is not None else None


# --- Precios de suministro ---


async def _verificar_propiedad_suministro(
    session: AsyncSession, suministro_id: uuid.UUID, alcance: Alcance, principal: Principal
) -> None:
    suministro = await service.obtener_suministro(session, suministro_id)
    if suministro is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarifa no encontrada")
    producto = await service.obtener_producto(session, suministro.producto_id)
    verificar_propiedad(alcance, principal, producto.creado_por_subject if producto else None)


@suministros_router.patch("/{suministro_id}", response_model=PrecioSuministroOut)
async def actualizar_suministro(
    suministro_id: uuid.UUID,
    datos: PrecioSuministroUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
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
    alcance: Alcance = Depends(require_permiso("catalogo", "editar")),
) -> None:
    await _verificar_propiedad_suministro(session, suministro_id, alcance, principal)
    await service.eliminar_suministro(session, suministro_id)


router = APIRouter()
router.include_router(productos_router)
router.include_router(familias_router)
router.include_router(suministros_router)
