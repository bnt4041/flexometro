import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from app.modules.core import service as core_service
from app.modules.core import usuarios_service
from app.modules.core.permisos_schemas import ActualizarUsuarioIn, UsuarioKeycloakOut

router = APIRouter()


class CrearUsuarioIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    es_admin: bool = False


class ReenviarIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=100)


class UsuarioCreadoOut(BaseModel):
    keycloak_user_id: str
    username: str
    email: str
    email_enviado: bool


@router.post(
    "/organizaciones/{organization_id}/usuarios",
    response_model=UsuarioCreadoOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_usuario_administrador(
    organization_id: uuid.UUID,
    datos: CrearUsuarioIn,
    session: AsyncSession = Depends(get_session),
) -> UsuarioCreadoOut:
    organizacion = await core_service.obtener_organizacion(session, organization_id)
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return UsuarioCreadoOut(
        keycloak_user_id=user_id,
        username=datos.username,
        email=datos.email,
        email_enviado=email_enviado,
    )


@router.post(
    "/organizaciones/{organization_id}/usuarios/{keycloak_user_id}/reenviar",
    response_model=UsuarioCreadoOut,
)
async def reenviar_bienvenida(
    organization_id: uuid.UUID,
    keycloak_user_id: str,
    datos: ReenviarIn,
    session: AsyncSession = Depends(get_session),
) -> UsuarioCreadoOut:
    organizacion = await core_service.obtener_organizacion(session, organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")

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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return UsuarioCreadoOut(
        keycloak_user_id=keycloak_user_id,
        username=datos.username,
        email=datos.email,
        email_enviado=email_enviado,
    )


@router.get(
    "/organizaciones/{organization_id}/usuarios",
    response_model=list[UsuarioKeycloakOut],
)
async def listar_usuarios(
    organization_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[UsuarioKeycloakOut]:
    organizacion = await core_service.obtener_organizacion(session, organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")

    cliente_kc = KeycloakAdminClient(get_settings())
    usuarios = await cliente_kc.listar_usuarios(organizacion.slug)
    return [UsuarioKeycloakOut(**usuario) for usuario in usuarios]


@router.patch(
    "/organizaciones/{organization_id}/usuarios/{keycloak_user_id}",
    response_model=UsuarioKeycloakOut,
)
async def actualizar_usuario(
    organization_id: uuid.UUID,
    keycloak_user_id: str,
    datos: ActualizarUsuarioIn,
    session: AsyncSession = Depends(get_session),
) -> UsuarioKeycloakOut:
    organizacion = await core_service.obtener_organizacion(session, organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")

    cliente_kc = KeycloakAdminClient(get_settings())
    try:
        usuario = await cliente_kc.actualizar_usuario(
            keycloak_user_id,
            email=datos.email,
            nombre=datos.nombre,
            apellidos=datos.apellidos,
            habilitado=datos.habilitado,
        )
    except KeycloakAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return UsuarioKeycloakOut(**usuario)


@router.delete(
    "/organizaciones/{organization_id}/usuarios/{keycloak_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def eliminar_usuario(
    organization_id: uuid.UUID,
    keycloak_user_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    organizacion = await core_service.obtener_organizacion(session, organization_id)
    if organizacion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organización no encontrada")

    cliente_kc = KeycloakAdminClient(get_settings())
    try:
        await cliente_kc.eliminar_usuario(keycloak_user_id)
    except KeycloakAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
