import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_superadmin
from app.core.database import get_session
from app.core.exportar_pdf import ExportacionDemasiadoGrande, generar_pdf_listado
from app.core.modules import registry
from app.modules.core import (
    ajustes_router,
    billing_router,
    creditos_router,
    cuenta_router,
    diccionario_router,
    moneda_router,
    permisos_router,
    personal_plataforma_router,
    service,
    settings_router,
    traduccion_router,
    usuarios_router,
)
from app.modules.core.admin_schemas import (
    OrganizacionDetalle,
    OrganizacionOut,
    OrganizacionUpdate,
)
from app.modules.core.service import active_module_codes, set_module_active

router = APIRouter(prefix="/api", tags=["core"])
admin_router = APIRouter(
    prefix="/admin",
    tags=["administración"],
    dependencies=[Depends(require_superadmin)],
)


class NavItemOut(BaseModel):
    label: str
    path: str
    icon: str


class ModuleOut(BaseModel):
    code: str
    name: str
    description: str
    icon: str
    depends_on: list[str]
    always_active: bool
    is_active: bool
    nav: list[NavItemOut]
    tipo_documento_numeracion: str | None


class PrincipalOut(BaseModel):
    username: str
    # None para el personal de la plataforma (rol superadmin sin
    # organización propia, ver Fase 13).
    organization_id: str | None
    organization_slug: str | None
    roles: list[str]
    # Organizaciones entre las que el usuario puede conmutar sin volver a
    # iniciar sesión, enviando la cabecera X-Organization-Slug.
    organizaciones: list[str]


@router.get("/me", response_model=PrincipalOut)
async def read_me(principal: Principal = Depends(get_principal)) -> PrincipalOut:
    return PrincipalOut(
        username=principal.username,
        organization_id=str(principal.organization_id) if principal.organization_id else None,
        organization_slug=principal.organization_slug,
        roles=sorted(principal.roles),
        organizaciones=sorted(principal.organizaciones),
    )


@router.get("/organizacion/logo")
async def logo_organizacion(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> Response:
    """El logo de la propia organización — cualquier usuario autenticado
    puede verlo (es de marca, no un dato sensible), no solo el admin que lo
    sube desde Ajustes."""
    if principal.organization_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin logo")
    logo = await service.logo_de_organizacion(session, principal.organization_id)
    if logo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin logo")
    contenido, content_type = logo
    return Response(content=contenido, media_type=content_type)


class ExportarPdfIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    columnas: list[str] = Field(min_length=1)
    filas: list[list[str]]


@router.post("/exportar/pdf")
async def exportar_pdf(
    datos: ExportarPdfIn, _principal: Principal = Depends(get_principal)
) -> Response:
    """Genérico para cualquier listado con `DataTable` (frontend) — exporta
    exactamente las columnas/filas que el navegador ya tiene en pantalla
    (filtradas, ordenadas, con las columnas visibles que toque), no vuelve a
    consultar nada: cualquier usuario autenticado puede pedirlo, no hace
    falta un permiso aparte porque no expone datos que no tuviera ya."""
    try:
        pdf = generar_pdf_listado(titulo=datos.titulo, columnas=datos.columnas, filas=datos.filas)
    except ExportacionDemasiadoGrande as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="listado.pdf"'},
    )


@router.get("/modules", response_model=list[ModuleOut])
async def list_modules(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[ModuleOut]:
    """Catálogo completo con su estado. El shell del frontend construye el menú
    a partir del `nav` de los módulos activos. El personal de la plataforma
    (sin organización) no tiene ninguno activo — su menú es solo
    Administración, que no pasa por aquí."""
    active = (
        await active_module_codes(session, principal.organization_id)
        if principal.organization_id is not None
        else set()
    )
    return [
        ModuleOut(
            code=spec.code,
            name=spec.name,
            description=spec.description,
            icon=spec.icon,
            depends_on=list(spec.depends_on),
            always_active=spec.always_active,
            is_active=spec.code in active,
            nav=[NavItemOut(label=n.label, path=n.path, icon=n.icon) for n in spec.nav],
            tipo_documento_numeracion=spec.tipo_documento_numeracion,
        )
        for spec in registry.all()
    ]


@router.post("/modules/{code}/activate", response_model=list[str])
async def activate_module(
    code: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    return await _toggle(session, principal, code, active=True)


@router.post("/modules/{code}/deactivate", response_model=list[str])
async def deactivate_module(
    code: str,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    return await _toggle(session, principal, code, active=False)


async def _toggle(
    session: AsyncSession, principal: Principal, code: str, active: bool
) -> list[str]:
    try:
        result = await set_module_active(session, principal.organization_id, code, active)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return sorted(result)


# --- Administración de organizaciones (rol superadmin) ---
#
# Mismo login que cualquier usuario de un tenant: estas rutas no tienen un
# mecanismo de autenticación aparte, solo exigen el rol 'superadmin' además
# de estar autenticado. No pasan por `require_module`: no son un módulo de
# negocio activable, es la propia administración de qué organizaciones y
# módulos existen.
#
# Desde la Fase 14 no hay alta ni listado plano de organizaciones aquí: toda
# organización nace dentro de una cuenta, ver `cuenta_router.py`
# (`/admin/cuentas/{id}/organizaciones`). Esto solo conserva el detalle de
# una organización YA creada.


@admin_router.get("/organizaciones/{organization_id}", response_model=OrganizacionDetalle)
async def detalle_organizacion(
    organization_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> OrganizacionDetalle:
    organizacion = await service.obtener_organizacion(session, organization_id)
    if organizacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada"
        )
    modulos = await service.estado_modulos(session, organization_id)
    return OrganizacionDetalle(
        **OrganizacionOut.model_validate(organizacion).model_dump(),
        settings=organizacion.settings,
        modulos=modulos,
    )


@admin_router.patch("/organizaciones/{organization_id}", response_model=OrganizacionOut)
async def actualizar_organizacion(
    organization_id: uuid.UUID,
    datos: OrganizacionUpdate,
    session: AsyncSession = Depends(get_session),
) -> OrganizacionOut:
    organizacion = await service.actualizar_organizacion(session, organization_id, datos)
    if organizacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada"
        )
    return OrganizacionOut.model_validate(organizacion)


@admin_router.post(
    "/organizaciones/{organization_id}/modulos/{code}/activate", response_model=list[str]
)
async def activar_modulo_organizacion(
    organization_id: uuid.UUID, code: str, session: AsyncSession = Depends(get_session)
) -> list[str]:
    return await _toggle_admin(session, organization_id, code, active=True)


@admin_router.post(
    "/organizaciones/{organization_id}/modulos/{code}/deactivate", response_model=list[str]
)
async def desactivar_modulo_organizacion(
    organization_id: uuid.UUID, code: str, session: AsyncSession = Depends(get_session)
) -> list[str]:
    return await _toggle_admin(session, organization_id, code, active=False)


async def _toggle_admin(
    session: AsyncSession, organization_id: uuid.UUID, code: str, active: bool
) -> list[str]:
    if await service.obtener_organizacion(session, organization_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada"
        )
    try:
        result = await service.set_module_active_admin(session, organization_id, code, active)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return sorted(result)


admin_router.include_router(billing_router.router)
admin_router.include_router(settings_router.router)
admin_router.include_router(usuarios_router.router)
admin_router.include_router(permisos_router.router)
admin_router.include_router(personal_plataforma_router.router)
admin_router.include_router(cuenta_router.router)
router.include_router(admin_router)
router.include_router(permisos_router.tenant_router)
router.include_router(ajustes_router.tenant_router)
router.include_router(diccionario_router.router)
router.include_router(diccionario_router.tenant_router)
router.include_router(traduccion_router.router)
router.include_router(traduccion_router.tenant_router)
router.include_router(moneda_router.router)
router.include_router(moneda_router.tenant_router)
router.include_router(creditos_router.router)
