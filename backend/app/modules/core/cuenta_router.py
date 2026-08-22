import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.numeracion import PatronInvalido
from app.modules.core import cuenta_service, service as core_service
from app.modules.core.admin_schemas import OrganizacionCreate, OrganizacionOut
from app.modules.core.cuenta_schemas import (
    CuentaCreate,
    CuentaDetalle,
    CuentaOut,
    CuentaUpdate,
    PatronNumeracionOut,
    PatronNumeracionUpdate,
)

router = APIRouter(prefix="/cuentas", tags=["cuentas"])


async def _detalle(session: AsyncSession, cuenta) -> CuentaDetalle:
    return CuentaDetalle(
        **CuentaOut.model_validate(cuenta).model_dump(),
        settings=cuenta.settings,
        cifs_distintos=await cuenta_service.cifs_distintos_de_cuenta(session, cuenta.id),
    )


@router.get("", response_model=list[CuentaOut])
async def listar_cuentas(session: AsyncSession = Depends(get_session)) -> list[CuentaOut]:
    return [CuentaOut.model_validate(c) for c in await cuenta_service.listar_cuentas(session)]


@router.post("", response_model=CuentaDetalle, status_code=status.HTTP_201_CREATED)
async def crear_cuenta(
    datos: CuentaCreate, session: AsyncSession = Depends(get_session)
) -> CuentaDetalle:
    cuenta = await cuenta_service.crear_cuenta(session, datos)
    return await _detalle(session, cuenta)


@router.get("/{cuenta_id}", response_model=CuentaDetalle)
async def detalle_cuenta(
    cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> CuentaDetalle:
    cuenta = await cuenta_service.obtener_cuenta(session, cuenta_id)
    if cuenta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    return await _detalle(session, cuenta)


@router.patch("/{cuenta_id}", response_model=CuentaDetalle)
async def actualizar_cuenta(
    cuenta_id: uuid.UUID, datos: CuentaUpdate, session: AsyncSession = Depends(get_session)
) -> CuentaDetalle:
    cuenta = await cuenta_service.actualizar_cuenta(session, cuenta_id, datos)
    if cuenta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    return await _detalle(session, cuenta)


# --- Organizaciones de la cuenta ---
#
# Una organización siempre nace dentro de una cuenta — no existe alta de
# organización sin elegir antes su cuenta, así que el alta cuelga de aquí en
# vez de ser una ruta propia como antes de la Fase 14.


@router.get("/{cuenta_id}/organizaciones", response_model=list[OrganizacionOut])
async def listar_organizaciones_de_cuenta(
    cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[OrganizacionOut]:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    organizaciones = await cuenta_service.organizaciones_de_cuenta(session, cuenta_id)
    return [OrganizacionOut.model_validate(o) for o in organizaciones]


@router.post(
    "/{cuenta_id}/organizaciones", response_model=OrganizacionOut, status_code=status.HTTP_201_CREATED
)
async def crear_organizacion_de_cuenta(
    cuenta_id: uuid.UUID, datos: OrganizacionCreate, session: AsyncSession = Depends(get_session)
) -> OrganizacionOut:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    organizacion = await core_service.crear_organizacion(session, cuenta_id, datos)
    return OrganizacionOut.model_validate(organizacion)


# --- Patrones de numeración (Fase 16) ---


@router.get("/{cuenta_id}/patrones-numeracion", response_model=list[PatronNumeracionOut])
async def listar_patrones_numeracion(
    cuenta_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[PatronNumeracionOut]:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    return await cuenta_service.listar_patrones_numeracion(session, cuenta_id)


@router.put(
    "/{cuenta_id}/patrones-numeracion/{tipo_documento}", response_model=PatronNumeracionOut
)
async def actualizar_patron_numeracion(
    cuenta_id: uuid.UUID,
    tipo_documento: str,
    datos: PatronNumeracionUpdate,
    session: AsyncSession = Depends(get_session),
) -> PatronNumeracionOut:
    if await cuenta_service.obtener_cuenta(session, cuenta_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cuenta no encontrada")
    try:
        return await cuenta_service.actualizar_patron_numeracion(session, cuenta_id, tipo_documento, datos)
    except PatronInvalido as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
