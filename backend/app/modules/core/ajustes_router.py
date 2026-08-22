"""Autoservicio de ajustes de módulo (Fase 17): el admin de organización edita
los ajustes de sus propios módulos (por ahora, el patrón de numeración de
presupuestos/albaranes/facturas) sin depender del superadmin.

Mismo patrón que `permisos_router.tenant_router`: gated por
`require_admin_organizacion`, resuelve `cuenta_id` a partir de
`principal.organization_id` — nunca lo acepta como parámetro de ruta, para no
poder cruzar la frontera de cuenta ajena.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.config import get_settings
from app.core.database import get_session
from app.core.keycloak_admin import KeycloakAdminClient
from app.core.numeracion import PatronInvalido
from app.modules.core import cuenta_service
from app.modules.core import service as core_service
from app.modules.core.cuenta_schemas import (
    EmpresaCrear,
    EmpresaOut,
    EmpresaResumenOut,
    EmpresaUpdate,
    EmpresasCuentaOut,
    PatronNumeracionOut,
    PatronNumeracionUpdate,
)
from app.modules.core.tenant_utils import cuenta_id_del_principal

logger = logging.getLogger("obras")

TAMANO_MAXIMO_LOGO = 3 * 1024 * 1024
TIPOS_LOGO_ADMITIDOS = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}

tenant_router = APIRouter(
    prefix="/ajustes", tags=["ajustes"], dependencies=[Depends(require_admin_organizacion)]
)


class NumeracionInfoOut(BaseModel):
    patrones: list[PatronNumeracionOut]
    cifs_distintos: bool


@tenant_router.get("/numeracion", response_model=NumeracionInfoOut)
async def numeracion_tenant(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> NumeracionInfoOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    return NumeracionInfoOut(
        patrones=await cuenta_service.listar_patrones_numeracion(session, cuenta_id),
        cifs_distintos=await cuenta_service.cifs_distintos_de_cuenta(session, cuenta_id),
    )


@tenant_router.put("/numeracion/{tipo_documento}", response_model=PatronNumeracionOut)
async def actualizar_numeracion_tenant(
    tipo_documento: str,
    datos: PatronNumeracionUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> PatronNumeracionOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        return await cuenta_service.actualizar_patron_numeracion(session, cuenta_id, tipo_documento, datos)
    except PatronInvalido as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _a_empresa_out(organizacion) -> EmpresaOut:
    return EmpresaOut(
        id=organizacion.id,
        name=organizacion.name,
        cif=organizacion.cif,
        direccion=organizacion.direccion,
        codigo_postal=organizacion.codigo_postal,
        ciudad=organizacion.ciudad,
        provincia=organizacion.provincia,
        telefono=organizacion.telefono,
        email=organizacion.email,
        web=organizacion.web,
        linkedin=organizacion.linkedin,
        instagram=organizacion.instagram,
        facebook=organizacion.facebook,
        twitter=organizacion.twitter,
        politica_privacidad=organizacion.politica_privacidad,
        tiene_logo=organizacion.logo_object_key is not None,
    )


async def _empresa_propia_o_404(session, cuenta_id, organization_id):
    organizacion = await cuenta_service.empresa_de_cuenta(session, cuenta_id, organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    return organizacion


# --- Empresas de la cuenta: cuáles hay y cuántas más se pueden crear (Fase 41) ---


@tenant_router.get("/empresas", response_model=EmpresasCuentaOut)
async def empresas_tenant(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> EmpresasCuentaOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    cuenta = await cuenta_service.obtener_cuenta(session, cuenta_id)
    organizaciones = await cuenta_service.organizaciones_de_cuenta(session, cuenta_id)
    return EmpresasCuentaOut(
        empresas=[
            EmpresaResumenOut(
                id=o.id,
                slug=o.slug,
                name=o.name,
                cif=o.cif,
                is_active=o.is_active,
                es_la_actual=(o.id == principal.organization_id),
            )
            for o in organizaciones
        ],
        max_organizaciones=cuenta.max_organizaciones,
        puede_crear=len(organizaciones) < cuenta.max_organizaciones,
    )


@tenant_router.post("/empresas", response_model=EmpresaResumenOut, status_code=status.HTTP_201_CREATED)
async def crear_empresa_tenant(
    datos: EmpresaCrear,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EmpresaResumenOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        organizacion = await cuenta_service.crear_empresa_autoservicio(session, cuenta_id, datos)
    except cuenta_service.LimiteEmpresasSuperado as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # El admin que la crea gana acceso a las dos: sin esto, la empresa nueva
    # quedaría inaccesible hasta que alguien la conceda a mano en Keycloak.
    try:
        await KeycloakAdminClient(get_settings()).anadir_organizacion(principal.subject, organizacion.slug)
    except Exception:
        logger.warning(
            "Empresa '%s' creada pero no se pudo conceder acceso automático en Keycloak",
            organizacion.slug,
            exc_info=True,
        )

    return EmpresaResumenOut(
        id=organizacion.id,
        slug=organizacion.slug,
        name=organizacion.name,
        cif=organizacion.cif,
        is_active=organizacion.is_active,
        es_la_actual=False,
    )


# --- Ficha de una empresa concreta: cualquiera de la propia cuenta, no solo
# la activa en la sesión (Fase 41 — pestañas de Ajustes -> Empresa) ---


@tenant_router.get("/empresas/{organization_id}", response_model=EmpresaOut)
async def empresa_tenant(
    organization_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EmpresaOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    organizacion = await _empresa_propia_o_404(session, cuenta_id, organization_id)
    return _a_empresa_out(organizacion)


@tenant_router.patch("/empresas/{organization_id}", response_model=EmpresaOut)
async def actualizar_empresa_tenant(
    organization_id: uuid.UUID,
    datos: EmpresaUpdate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EmpresaOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    await _empresa_propia_o_404(session, cuenta_id, organization_id)
    organizacion = await core_service.actualizar_organizacion(session, organization_id, datos)
    return _a_empresa_out(organizacion)


@tenant_router.get("/empresas/{organization_id}/logo")
async def logo_empresa_tenant(
    organization_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    await _empresa_propia_o_404(session, cuenta_id, organization_id)
    logo = await core_service.logo_de_organizacion(session, organization_id)
    if logo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin logo")
    contenido, content_type = logo
    return Response(content=contenido, media_type=content_type)


@tenant_router.post("/empresas/{organization_id}/logo", response_model=EmpresaOut)
async def subir_logo_tenant(
    organization_id: uuid.UUID,
    archivo: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EmpresaOut:
    if archivo.content_type not in TIPOS_LOGO_ADMITIDOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El logo debe ser PNG, JPEG, WebP o SVG",
        )
    contenido = await archivo.read()
    if len(contenido) > TAMANO_MAXIMO_LOGO:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El logo supera los 3 MB")

    cuenta_id = await cuenta_id_del_principal(session, principal)
    await _empresa_propia_o_404(session, cuenta_id, organization_id)
    organizacion = await core_service.subir_logo_organizacion(
        session, organization_id, contenido, archivo.content_type
    )
    return _a_empresa_out(organizacion)


@tenant_router.delete("/empresas/{organization_id}/logo", response_model=EmpresaOut)
async def eliminar_logo_tenant(
    organization_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> EmpresaOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    await _empresa_propia_o_404(session, cuenta_id, organization_id)
    organizacion = await core_service.eliminar_logo_organizacion(session, organization_id)
    return _a_empresa_out(organizacion)
