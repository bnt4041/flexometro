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
from app.modules.contratos import service
from app.modules.contratos.models import Contrato, TipoContrato
from app.modules.contratos.schemas import (
    ContratoCreate,
    ContratoOut,
    ContratoResumen,
    ContratoUpdate,
)
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut

guard = Depends(require_module("contratos"))
router = APIRouter(prefix="/api/contratos", tags=["contratos"], dependencies=[guard])


@router.get("", response_model=Page[ContratoResumen])
async def listar(
    obra_id: uuid.UUID | None = None,
    tipo: TipoContrato | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("contratos", "ver")),
) -> Page[ContratoResumen]:
    filas, total = await service.listar(
        session,
        obra_id=obra_id,
        tipo=tipo,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    items = [
        ContratoResumen(
            **ContratoOut.model_validate(contrato).model_dump(),
            tercero_razon_social=razon_social,
        )
        for contrato, razon_social in filas
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ContratoOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: ContratoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("contratos", "editar")),
) -> ContratoOut:
    try:
        contrato = await service.crear(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (service.ObraInvalida, service.TerceroInvalido, service.PresupuestoInvalido) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ContratoOut.model_validate(contrato)


async def _contrato_propio(
    session: AsyncSession, contrato_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    resultado = await service.obtener(session, contrato_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contrato no encontrado")
    contrato, razon_social = resultado
    verificar_propiedad(alcance, principal, contrato.creado_por_subject)
    return contrato, razon_social


@router.get("/{contrato_id}", response_model=ContratoResumen)
async def detalle(
    contrato_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("contratos", "ver")),
) -> ContratoResumen:
    contrato, razon_social = await _contrato_propio(session, contrato_id, alcance, principal)
    return ContratoResumen(
        **ContratoOut.model_validate(contrato).model_dump(),
        tercero_razon_social=razon_social,
    )


@router.get("/{contrato_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    contrato_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("contratos", "ver")),
) -> list[RegistroAuditoriaOut]:
    await _contrato_propio(session, contrato_id, alcance, principal)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Contrato), registro_id=contrato_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@router.patch("/{contrato_id}", response_model=ContratoOut)
async def actualizar(
    contrato_id: uuid.UUID,
    datos: ContratoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("contratos", "editar")),
) -> ContratoOut:
    await _contrato_propio(session, contrato_id, alcance, principal)
    try:
        contrato = await service.actualizar(session, contrato_id, datos)
    except service.PresupuestoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert contrato is not None
    return ContratoOut.model_validate(contrato)


@router.delete("/{contrato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    contrato_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("contratos", "editar")),
) -> None:
    await _contrato_propio(session, contrato_id, alcance, principal)
    await service.eliminar(session, contrato_id)
