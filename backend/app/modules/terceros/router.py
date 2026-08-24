import uuid
from typing import Literal

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
from app.modules.terceros import apariciones_service, service
from app.modules.terceros.models import Contacto, EntidadContacto, Tercero
from app.modules.terceros.apariciones_schemas import AparicionOut
from app.modules.terceros.schemas import (
    ContactoAsociadoCreate,
    ContactoAsociadoOut,
    ContactoCreate,
    ContactoOut,
    ContactoUpdate,
    CuentaBancariaTerceroCreate,
    CuentaBancariaTerceroOut,
    CuentaBancariaTerceroUpdate,
    TerceroCreate,
    TerceroDetalle,
    TerceroOut,
    TerceroUpdate,
)

terceros_router = APIRouter(
    prefix="/api/terceros",
    tags=["terceros"],
    dependencies=[Depends(require_module("terceros"))],
)


@terceros_router.get("", response_model=Page[TerceroOut])
async def listar(
    q: str | None = Query(default=None, description="Busca en razón social, NIF y código"),
    rol: Literal["cliente", "proveedor", "subcontratista"] | None = None,
    activo: bool | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> Page[TerceroOut]:
    items, total = await service.listar_terceros(
        session,
        q=q,
        rol=rol,
        activo=activo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[TerceroOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@terceros_router.post("", response_model=TerceroDetalle, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: TerceroCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> TerceroDetalle:
    try:
        tercero = await service.crear_tercero(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TerceroDetalle.model_validate(tercero)


@terceros_router.get("/siguiente-codigo", response_model=str)
async def siguiente_codigo(session: AsyncSession = Depends(get_session)) -> str:
    return await service.siguiente_codigo(session)


@terceros_router.get("/{tercero_id}", response_model=TerceroDetalle)
async def detalle(
    tercero_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> TerceroDetalle:
    tercero = await service.obtener_tercero_visible(session, tercero_id)
    if tercero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero no encontrado")
    verificar_propiedad(alcance, principal, tercero.creado_por_subject)
    return TerceroDetalle.model_validate(tercero)


@terceros_router.get("/{tercero_id}/apariciones", response_model=list[AparicionOut])
async def apariciones(
    tercero_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> list[AparicionOut]:
    tercero = await service.obtener_tercero_visible(session, tercero_id)
    if tercero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero no encontrado")
    verificar_propiedad(alcance, principal, tercero.creado_por_subject)
    return await apariciones_service.apariciones_de(session, tercero_id)


@terceros_router.get("/{tercero_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    tercero_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> list[RegistroAuditoriaOut]:
    tercero = await service.obtener_tercero_visible(session, tercero_id)
    if tercero is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero no encontrado")
    verificar_propiedad(alcance, principal, tercero.creado_por_subject)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Tercero), registro_id=tercero_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@terceros_router.patch("/{tercero_id}", response_model=TerceroOut)
async def actualizar(
    tercero_id: uuid.UUID,
    datos: TerceroUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> TerceroOut:
    existente = await service.obtener_tercero(session, tercero_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    tercero = await service.actualizar_tercero(session, tercero_id, datos)
    return TerceroOut.model_validate(tercero)


@terceros_router.delete("/{tercero_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    tercero_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> None:
    existente = await service.obtener_tercero(session, tercero_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tercero no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    await service.eliminar_tercero(session, tercero_id)


# --- Contactos ---

contactos_router = APIRouter(
    prefix="/api/contactos",
    tags=["terceros"],
    dependencies=[Depends(require_module("terceros"))],
)


@contactos_router.get("", response_model=Page[ContactoOut])
async def listar_contactos(
    tercero_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> Page[ContactoOut]:
    items, total = await service.listar_contactos(
        session,
        tercero_id=tercero_id,
        q=q,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[ContactoOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@contactos_router.post("", response_model=ContactoOut, status_code=status.HTTP_201_CREATED)
async def crear_contacto(
    datos: ContactoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> ContactoOut:
    contacto = await service.crear_contacto(session, datos)
    return ContactoOut.model_validate(contacto)


@contactos_router.get("/{contacto_id}", response_model=ContactoOut)
async def detalle_contacto(
    contacto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> ContactoOut:
    contacto = await service.obtener_contacto_visible(session, contacto_id)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    verificar_propiedad(alcance, principal, contacto.creado_por_subject)
    return ContactoOut.model_validate(contacto)


@contactos_router.get("/{contacto_id}/apariciones", response_model=list[AparicionOut])
async def apariciones_contacto(
    contacto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> list[AparicionOut]:
    contacto = await service.obtener_contacto_visible(session, contacto_id)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    verificar_propiedad(alcance, principal, contacto.creado_por_subject)
    return await apariciones_service.apariciones_de_contacto(session, contacto_id)


@contactos_router.get("/{contacto_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial_contacto(
    contacto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> list[RegistroAuditoriaOut]:
    contacto = await service.obtener_contacto_visible(session, contacto_id)
    if contacto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    verificar_propiedad(alcance, principal, contacto.creado_por_subject)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Contacto), registro_id=contacto_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@contactos_router.patch("/{contacto_id}", response_model=ContactoOut)
async def actualizar_contacto(
    contacto_id: uuid.UUID,
    datos: ContactoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> ContactoOut:
    existente = await service.obtener_contacto(session, contacto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    contacto = await service.actualizar_contacto(session, contacto_id, datos)
    return ContactoOut.model_validate(contacto)


@contactos_router.delete("/{contacto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_contacto(
    contacto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> None:
    existente = await service.obtener_contacto(session, contacto_id)
    if existente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contacto no encontrado")
    verificar_propiedad(alcance, principal, existente.creado_por_subject)
    await service.eliminar_contacto(session, contacto_id)


# --- Contactos asociados (Fase 28) ---

contactos_asociados_router = APIRouter(
    prefix="/api/contactos-asociados",
    tags=["terceros"],
    dependencies=[Depends(require_module("terceros"))],
)


def _asociado_a_out(asociado) -> ContactoAsociadoOut:
    contacto = asociado.contacto
    return ContactoAsociadoOut(
        id=asociado.id,
        entidad=asociado.entidad,
        entidad_id=asociado.entidad_id,
        contacto_id=asociado.contacto_id,
        rol=asociado.rol,
        created_at=asociado.created_at,
        contacto_nombre=contacto.nombre,
        contacto_apellidos=contacto.apellidos,
        contacto_cargo=contacto.cargo,
        contacto_email=contacto.email,
        contacto_telefono=contacto.telefono,
    )


@contactos_asociados_router.get("", response_model=list[ContactoAsociadoOut])
async def listar_asociados(
    entidad: EntidadContacto,
    entidad_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> list[ContactoAsociadoOut]:
    asociados = await service.listar_asociados(session, entidad, entidad_id)
    return [_asociado_a_out(a) for a in asociados]


@contactos_asociados_router.post(
    "", response_model=ContactoAsociadoOut, status_code=status.HTTP_201_CREATED
)
async def asociar_contacto(
    entidad: EntidadContacto,
    entidad_id: uuid.UUID,
    datos: ContactoAsociadoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> ContactoAsociadoOut:
    try:
        asociado = await service.asociar_contacto(session, entidad, entidad_id, datos)
    except service.AsociacionDuplicada as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _asociado_a_out(asociado)


@contactos_asociados_router.delete("/{asociacion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_asociacion(
    asociacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> None:
    encontrado = await service.eliminar_asociacion(session, asociacion_id)
    if not encontrado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asociación no encontrada")


# --- Cuentas bancarias de terceros (Fase 47) ---

cuentas_bancarias_router = APIRouter(
    prefix="/api/terceros/{tercero_id}/cuentas-bancarias",
    tags=["terceros"],
    dependencies=[Depends(require_module("terceros"))],
)


@cuentas_bancarias_router.get("", response_model=list[CuentaBancariaTerceroOut])
async def listar_cuentas_bancarias(
    tercero_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "ver")),
) -> list[CuentaBancariaTerceroOut]:
    cuentas = await service.listar_cuentas_bancarias(session, tercero_id)
    return [CuentaBancariaTerceroOut.model_validate(c) for c in cuentas]


@cuentas_bancarias_router.post(
    "", response_model=CuentaBancariaTerceroOut, status_code=status.HTTP_201_CREATED
)
async def crear_cuenta_bancaria(
    tercero_id: uuid.UUID,
    datos: CuentaBancariaTerceroCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> CuentaBancariaTerceroOut:
    if datos.tercero_id != tercero_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El tercero de la ruta no coincide con el del cuerpo",
        )
    cuenta = await service.crear_cuenta_bancaria(session, datos)
    return CuentaBancariaTerceroOut.model_validate(cuenta)


@cuentas_bancarias_router.patch("/{cuenta_id}", response_model=CuentaBancariaTerceroOut)
async def actualizar_cuenta_bancaria(
    tercero_id: uuid.UUID,
    cuenta_id: uuid.UUID,
    datos: CuentaBancariaTerceroUpdate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> CuentaBancariaTerceroOut:
    cuenta = await service.actualizar_cuenta_bancaria(session, cuenta_id, datos)
    if cuenta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    return CuentaBancariaTerceroOut.model_validate(cuenta)


@cuentas_bancarias_router.delete("/{cuenta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_cuenta_bancaria(
    tercero_id: uuid.UUID,
    cuenta_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("terceros", "editar")),
) -> None:
    encontrado = await service.eliminar_cuenta_bancaria(session, cuenta_id)
    if not encontrado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")


# Router del módulo: FastAPI monta un único router por módulo, así que se
# agregan aquí los cuatro grupos de endpoints (prefijos distintos, mismo módulo).
router = APIRouter()
router.include_router(terceros_router)
router.include_router(contactos_router)
router.include_router(contactos_asociados_router)
router.include_router(cuentas_bancarias_router)
