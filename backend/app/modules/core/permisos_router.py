"""Endpoints de Grupos y Usuarios de la Fase 12, en dos sabores:

- `router` (superadmin): opera sobre cualquier organización, recibida como
  `organization_id` en la ruta. Se monta bajo `admin_router`
  (`require_superadmin`) en `router.py`. Antes de tocar `Grupo`/
  `GrupoPermiso`/`GrupoUsuario` —protegidas con RLS— hay que apuntar la
  sesión a esa organización con `fijar_organizacion_activa`, igual que hace
  `service.estado_modulos` para `organization_module`.
- `tenant_router` (autoservicio): opera siempre sobre la organización del
  propio principal, sin parámetro de ruta. Se monta bajo el `router` normal
  (`/api`), gated por `require_admin_organizacion`. No hace falta
  `fijar_organizacion_activa`: la sesión ya ve su propia organización como
  cualquier request normal, RLS de por medio.

Los usuarios de Keycloak (crear/listar/editar/borrar/reenviar invitación) del
lado autoservicio viven aquí también en vez de en `usuarios_router.py`,
porque ese archivo está montado íntegro bajo `admin_router` y todas sus rutas
heredan `require_superadmin` — no se puede reutilizar para el tenant sin
mezclar las dos guardas.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.config import get_settings
from app.core.database import fijar_organizacion_activa, get_session
from app.core.keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from app.core.modules import registry
from app.modules.core import permisos_service, service as core_service, usuarios_service
from app.modules.core.permisos_schemas import (
    ActualizarUsuarioIn,
    AnadirMiembroIn,
    EstablecerPermisosIn,
    GrupoCreate,
    GrupoDetalle,
    GrupoUpdate,
    ModuloDisponibleOut,
    UsuarioKeycloakOut,
)

router = APIRouter()
tenant_router = APIRouter(dependencies=[Depends(require_admin_organizacion)])


class CrearUsuarioTenantIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    es_admin: bool = False


class ReenviarTenantIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=100)


class UsuarioCreadoOut(BaseModel):
    keycloak_user_id: str
    username: str
    email: str
    email_enviado: bool


def _modulos_disponibles_out() -> list[ModuloDisponibleOut]:
    return [ModuloDisponibleOut(code=spec.code, name=spec.name) for spec in registry.all()]


# --- Superadmin: /admin/organizaciones/{organization_id}/grupos ---


@router.get("/organizaciones/{organization_id}/modulos-disponibles", response_model=list[ModuloDisponibleOut])
async def modulos_disponibles_admin(organization_id: uuid.UUID) -> list[ModuloDisponibleOut]:
    return _modulos_disponibles_out()


@router.get("/organizaciones/{organization_id}/grupos", response_model=list[GrupoDetalle])
async def listar_grupos_admin(
    organization_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[GrupoDetalle]:
    await fijar_organizacion_activa(session, organization_id)
    grupos = await permisos_service.listar_grupos(session, organization_id)
    return [GrupoDetalle.model_validate(g) for g in grupos]


@router.post(
    "/organizaciones/{organization_id}/grupos",
    response_model=GrupoDetalle,
    status_code=status.HTTP_201_CREATED,
)
async def crear_grupo_admin(
    organization_id: uuid.UUID, datos: GrupoCreate, session: AsyncSession = Depends(get_session)
) -> GrupoDetalle:
    await fijar_organizacion_activa(session, organization_id)
    try:
        grupo = await permisos_service.crear_grupo(
            session, organization_id, nombre=datos.nombre, descripcion=datos.descripcion
        )
    except permisos_service.NombreDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return GrupoDetalle.model_validate(grupo)


@router.patch("/organizaciones/{organization_id}/grupos/{grupo_id}", response_model=GrupoDetalle)
async def actualizar_grupo_admin(
    organization_id: uuid.UUID,
    grupo_id: uuid.UUID,
    datos: GrupoUpdate,
    session: AsyncSession = Depends(get_session),
) -> GrupoDetalle:
    await fijar_organizacion_activa(session, organization_id)
    grupo = await permisos_service.actualizar_grupo(
        session, grupo_id, nombre=datos.nombre, descripcion=datos.descripcion
    )
    if grupo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
    return GrupoDetalle.model_validate(grupo)


@router.delete(
    "/organizaciones/{organization_id}/grupos/{grupo_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def eliminar_grupo_admin(
    organization_id: uuid.UUID, grupo_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    await fijar_organizacion_activa(session, organization_id)
    if not await permisos_service.eliminar_grupo(session, grupo_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")


@router.put(
    "/organizaciones/{organization_id}/grupos/{grupo_id}/permisos", response_model=GrupoDetalle
)
async def establecer_permisos_admin(
    organization_id: uuid.UUID,
    grupo_id: uuid.UUID,
    datos: EstablecerPermisosIn,
    session: AsyncSession = Depends(get_session),
) -> GrupoDetalle:
    await fijar_organizacion_activa(session, organization_id)
    grupo = await permisos_service.establecer_permisos(
        session, grupo_id, [p.model_dump() for p in datos.permisos]
    )
    if grupo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
    return GrupoDetalle.model_validate(grupo)


@router.post(
    "/organizaciones/{organization_id}/grupos/{grupo_id}/miembros",
    response_model=GrupoDetalle,
    status_code=status.HTTP_201_CREATED,
)
async def anadir_miembro_admin(
    organization_id: uuid.UUID,
    grupo_id: uuid.UUID,
    datos: AnadirMiembroIn,
    session: AsyncSession = Depends(get_session),
) -> GrupoDetalle:
    await fijar_organizacion_activa(session, organization_id)
    try:
        await permisos_service.anadir_miembro(
            session,
            grupo_id,
            usuario_subject=datos.usuario_subject,
            usuario_nombre=datos.usuario_nombre,
        )
    except permisos_service.GrupoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except permisos_service.MiembroYaEnGrupo as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    grupo = await permisos_service.obtener_grupo(session, grupo_id)
    return GrupoDetalle.model_validate(grupo)


@router.delete(
    "/organizaciones/{organization_id}/grupos/{grupo_id}/miembros/{grupo_usuario_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def quitar_miembro_admin(
    organization_id: uuid.UUID,
    grupo_id: uuid.UUID,
    grupo_usuario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await fijar_organizacion_activa(session, organization_id)
    if not await permisos_service.quitar_miembro(session, grupo_usuario_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado")


# --- Tenant: /grupos y /usuarios (autoservicio, rol admin, propia organización) ---


@tenant_router.get("/modulos-disponibles", response_model=list[ModuloDisponibleOut])
async def modulos_disponibles_tenant() -> list[ModuloDisponibleOut]:
    return _modulos_disponibles_out()


@tenant_router.get("/grupos", response_model=list[GrupoDetalle])
async def listar_grupos_tenant(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> list[GrupoDetalle]:
    grupos = await permisos_service.listar_grupos(session, principal.organization_id)
    return [GrupoDetalle.model_validate(g) for g in grupos]


@tenant_router.post("/grupos", response_model=GrupoDetalle, status_code=status.HTTP_201_CREATED)
async def crear_grupo_tenant(
    datos: GrupoCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> GrupoDetalle:
    try:
        grupo = await permisos_service.crear_grupo(
            session, principal.organization_id, nombre=datos.nombre, descripcion=datos.descripcion
        )
    except permisos_service.NombreDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return GrupoDetalle.model_validate(grupo)


@tenant_router.patch("/grupos/{grupo_id}", response_model=GrupoDetalle)
async def actualizar_grupo_tenant(
    grupo_id: uuid.UUID, datos: GrupoUpdate, session: AsyncSession = Depends(get_session)
) -> GrupoDetalle:
    grupo = await permisos_service.actualizar_grupo(
        session, grupo_id, nombre=datos.nombre, descripcion=datos.descripcion
    )
    if grupo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
    return GrupoDetalle.model_validate(grupo)


@tenant_router.delete("/grupos/{grupo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_grupo_tenant(
    grupo_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    if not await permisos_service.eliminar_grupo(session, grupo_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")


@tenant_router.put("/grupos/{grupo_id}/permisos", response_model=GrupoDetalle)
async def establecer_permisos_tenant(
    grupo_id: uuid.UUID, datos: EstablecerPermisosIn, session: AsyncSession = Depends(get_session)
) -> GrupoDetalle:
    grupo = await permisos_service.establecer_permisos(
        session, grupo_id, [p.model_dump() for p in datos.permisos]
    )
    if grupo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
    return GrupoDetalle.model_validate(grupo)


@tenant_router.post(
    "/grupos/{grupo_id}/miembros", response_model=GrupoDetalle, status_code=status.HTTP_201_CREATED
)
async def anadir_miembro_tenant(
    grupo_id: uuid.UUID, datos: AnadirMiembroIn, session: AsyncSession = Depends(get_session)
) -> GrupoDetalle:
    try:
        await permisos_service.anadir_miembro(
            session,
            grupo_id,
            usuario_subject=datos.usuario_subject,
            usuario_nombre=datos.usuario_nombre,
        )
    except permisos_service.GrupoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except permisos_service.MiembroYaEnGrupo as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    grupo = await permisos_service.obtener_grupo(session, grupo_id)
    return GrupoDetalle.model_validate(grupo)


@tenant_router.delete(
    "/grupos/{grupo_id}/miembros/{grupo_usuario_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def quitar_miembro_tenant(
    grupo_id: uuid.UUID, grupo_usuario_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> None:
    if not await permisos_service.quitar_miembro(session, grupo_usuario_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado")


# --- Tenant: usuarios de la propia organización ---


@tenant_router.get("/usuarios", response_model=list[UsuarioKeycloakOut])
async def listar_usuarios_tenant(principal: Principal = Depends(get_principal)) -> list[UsuarioKeycloakOut]:
    cliente_kc = KeycloakAdminClient(get_settings())
    usuarios = await cliente_kc.listar_usuarios(principal.organization_slug)
    return [UsuarioKeycloakOut(**usuario) for usuario in usuarios]


@tenant_router.post(
    "/usuarios", response_model=UsuarioCreadoOut, status_code=status.HTTP_201_CREATED
)
async def crear_usuario_tenant(
    datos: CrearUsuarioTenantIn,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> UsuarioCreadoOut:
    organizacion = await core_service.obtener_organizacion(session, principal.organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    try:
        user_id, email_enviado = await usuarios_service.crear_usuario_administrador(
            session,
            organizacion,
            username=datos.username,
            email=datos.email,
            nombre=datos.nombre,
            apellidos=datos.apellidos,
            es_admin=datos.es_admin,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return UsuarioCreadoOut(
        keycloak_user_id=user_id, username=datos.username, email=datos.email, email_enviado=email_enviado
    )


async def _verificar_usuario_de_la_organizacion(cliente_kc: KeycloakAdminClient, keycloak_user_id: str, principal: Principal) -> None:
    if not await cliente_kc.pertenece_a_organizacion(keycloak_user_id, principal.organization_slug):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")


@tenant_router.post("/usuarios/{keycloak_user_id}/reenviar", response_model=UsuarioCreadoOut)
async def reenviar_bienvenida_tenant(
    keycloak_user_id: str,
    datos: ReenviarTenantIn,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> UsuarioCreadoOut:
    organizacion = await core_service.obtener_organizacion(session, principal.organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")
    await _verificar_usuario_de_la_organizacion(
        KeycloakAdminClient(get_settings()), keycloak_user_id, principal
    )
    try:
        email_enviado = await usuarios_service.reenviar_bienvenida(
            session,
            organizacion,
            keycloak_user_id=keycloak_user_id,
            username=datos.username,
            email=datos.email,
            nombre=datos.nombre,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return UsuarioCreadoOut(
        keycloak_user_id=keycloak_user_id,
        username=datos.username,
        email=datos.email,
        email_enviado=email_enviado,
    )


@tenant_router.patch("/usuarios/{keycloak_user_id}", response_model=UsuarioKeycloakOut)
async def actualizar_usuario_tenant(
    keycloak_user_id: str,
    datos: ActualizarUsuarioIn,
    principal: Principal = Depends(get_principal),
) -> UsuarioKeycloakOut:
    cliente_kc = KeycloakAdminClient(get_settings())
    await _verificar_usuario_de_la_organizacion(cliente_kc, keycloak_user_id, principal)
    try:
        usuario = await cliente_kc.actualizar_usuario(
            keycloak_user_id,
            email=datos.email,
            nombre=datos.nombre,
            apellidos=datos.apellidos,
            habilitado=datos.habilitado,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return UsuarioKeycloakOut(**usuario)


@tenant_router.delete("/usuarios/{keycloak_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_usuario_tenant(
    keycloak_user_id: str, principal: Principal = Depends(get_principal)
) -> None:
    cliente_kc = KeycloakAdminClient(get_settings())
    await _verificar_usuario_de_la_organizacion(cliente_kc, keycloak_user_id, principal)
    try:
        await cliente_kc.eliminar_usuario(keycloak_user_id)
    except KeycloakAdminError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
