"""El vínculo entre organizaciones.

`require_permiso` cubre el módulo, pero no basta por sí solo aquí: casi
todos los endpoints de vínculo comprueban ADEMÁS que quien llama es
participante de la fila (origen o destino), porque RLS ya solo deja ver esas
filas pero no distingue de qué lado estás — eso lo decide `service.py`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.core.tenancy import require_organization_id
from app.modules.plexo import service
from app.modules.plexo.enums import EstadoVinculo
from app.modules.plexo.models import Vinculo
from app.modules.plexo.schemas import (
    InvitarIn,
    OrganizacionPublicaOut,
    PerfilIn,
    PerfilOut,
    VinculoOut,
)

router = APIRouter(
    prefix="/api/plexo", tags=["plexo"], dependencies=[Depends(require_module("plexo"))]
)


@router.get("/perfil", response_model=PerfilOut)
async def ver_perfil(
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("plexo", "ver")),
) -> PerfilOut:
    return PerfilOut.model_validate(await service.mi_perfil(session))


@router.put("/perfil", response_model=PerfilOut)
async def fijar_perfil(
    datos: PerfilIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("plexo", "editar")),
) -> PerfilOut:
    return PerfilOut.model_validate(await service.fijar_visibilidad(session, datos.visible))


@router.get("/buscar", response_model=list[OrganizacionPublicaOut])
async def buscar(
    q: str,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("plexo", "ver")),
) -> list[OrganizacionPublicaOut]:
    return [OrganizacionPublicaOut.model_validate(o) for o in await service.buscar(session, q)]


@router.get("/vinculos", response_model=list[VinculoOut])
async def listar_vinculos(
    estado: EstadoVinculo | None = None,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("plexo", "ver")),
) -> list[VinculoOut]:
    org_id = require_organization_id()
    filas = await service.listar_vinculos(session, estado)
    return [await _salida(session, v, org_id) for v in filas]


@router.post("/vinculos", response_model=VinculoOut, status_code=status.HTTP_201_CREATED)
async def invitar(
    datos: InvitarIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("plexo", "crear")),
) -> VinculoOut:
    try:
        vinculo = await service.invitar(
            session, principal, datos.organizacion_destino_id, datos.mensaje
        )
    except service.PlexoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _salida(session, vinculo, require_organization_id())


@router.post("/vinculos/{vinculo_id}/aceptar", response_model=VinculoOut)
async def aceptar(
    vinculo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("plexo", "editar")),
) -> VinculoOut:
    vinculo = await _obtener_o_404(session, vinculo_id)
    try:
        await service.aceptar(session, principal, vinculo)
    except service.PlexoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _salida(session, vinculo, require_organization_id())


@router.post("/vinculos/{vinculo_id}/rechazar", response_model=VinculoOut)
async def rechazar(
    vinculo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("plexo", "editar")),
) -> VinculoOut:
    vinculo = await _obtener_o_404(session, vinculo_id)
    try:
        await service.rechazar(session, principal, vinculo)
    except service.PlexoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _salida(session, vinculo, require_organization_id())


@router.post("/vinculos/{vinculo_id}/revocar", response_model=VinculoOut)
async def revocar(
    vinculo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("plexo", "editar")),
) -> VinculoOut:
    vinculo = await _obtener_o_404(session, vinculo_id)
    try:
        await service.revocar(session, principal, vinculo)
    except service.PlexoError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return await _salida(session, vinculo, require_organization_id())


async def _obtener_o_404(session: AsyncSession, vinculo_id: uuid.UUID) -> Vinculo:
    vinculo = await service.obtener_vinculo(session, vinculo_id)
    if vinculo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return vinculo


async def _salida(session: AsyncSession, vinculo: Vinculo, org_id: uuid.UUID) -> VinculoOut:
    from app.modules.core.models import Organization

    soy_origen = vinculo.organizacion_origen_id == org_id
    otra_id = vinculo.organizacion_destino_id if soy_origen else vinculo.organizacion_origen_id
    otra = await session.get(Organization, otra_id)
    return VinculoOut(
        id=vinculo.id,
        estado=vinculo.estado,
        mensaje=vinculo.mensaje,
        otra_organizacion=OrganizacionPublicaOut.model_validate(otra),
        soy_quien_invito=soy_origen,
        invitado_por_nombre=vinculo.invitado_por_nombre,
        respondido_por_nombre=vinculo.respondido_por_nombre,
        created_at=vinculo.created_at,
        respondido_en=vinculo.respondido_en,
    )
