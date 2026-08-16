from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ROL_SUPERADMIN
from app.core.config import get_settings
from app.core.database import get_session
from app.core.keycloak_admin import KeycloakAdminClient, KeycloakAdminError
from app.modules.core import personal_plataforma_service
from app.modules.core.permisos_schemas import ActualizarUsuarioIn, UsuarioKeycloakOut

router = APIRouter(prefix="/personal-plataforma", tags=["personal de la plataforma"])


class CrearUsuarioPlataformaIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)


class ReenviarIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=100)


class UsuarioCreadoOut(BaseModel):
    keycloak_user_id: str
    username: str
    email: str
    email_enviado: bool


@router.get("", response_model=list[UsuarioKeycloakOut])
async def listar_personal_plataforma() -> list[UsuarioKeycloakOut]:
    cliente_kc = KeycloakAdminClient(get_settings())
    usuarios = await cliente_kc.listar_usuarios_por_rol(ROL_SUPERADMIN)
    return [UsuarioKeycloakOut(**usuario) for usuario in usuarios]


@router.post("", response_model=UsuarioCreadoOut, status_code=status.HTTP_201_CREATED)
async def crear_personal_plataforma(
    datos: CrearUsuarioPlataformaIn, session: AsyncSession = Depends(get_session)
) -> UsuarioCreadoOut:
    try:
        user_id, email_enviado = await personal_plataforma_service.crear_usuario_plataforma(
            session,
            username=datos.username,
            email=datos.email,
            nombre=datos.nombre,
            apellidos=datos.apellidos,
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


@router.post("/{keycloak_user_id}/reenviar", response_model=UsuarioCreadoOut)
async def reenviar_invitacion_plataforma(
    keycloak_user_id: str,
    datos: ReenviarIn,
    session: AsyncSession = Depends(get_session),
) -> UsuarioCreadoOut:
    try:
        email_enviado = await personal_plataforma_service.reenviar_bienvenida_plataforma(
            session,
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


@router.patch("/{keycloak_user_id}", response_model=UsuarioKeycloakOut)
async def actualizar_personal_plataforma(
    keycloak_user_id: str, datos: ActualizarUsuarioIn
) -> UsuarioKeycloakOut:
    cliente_kc = KeycloakAdminClient(get_settings())

    if datos.habilitado is False:
        await _rechazar_si_es_el_ultimo(cliente_kc, keycloak_user_id)

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


@router.delete("/{keycloak_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_personal_plataforma(keycloak_user_id: str) -> None:
    cliente_kc = KeycloakAdminClient(get_settings())
    await _rechazar_si_es_el_ultimo(cliente_kc, keycloak_user_id)

    try:
        await cliente_kc.eliminar_usuario(keycloak_user_id)
    except KeycloakAdminError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


async def _rechazar_si_es_el_ultimo(cliente_kc: KeycloakAdminClient, keycloak_user_id: str) -> None:
    """Sin esto, deshabilitar o borrar el único superadmin restante deja la
    plataforma sin nadie que pueda entrar a Administración a arreglarlo —
    hay que hacerlo desde la consola de Keycloak a mano, algo que conviene
    evitar de entrada en vez de documentar como "solución" del bloqueo."""
    usuarios = await cliente_kc.listar_usuarios_por_rol(ROL_SUPERADMIN)
    activos = [u for u in usuarios if u.get("enabled", True) and u["id"] != keycloak_user_id]
    if not activos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No puedes deshabilitar o eliminar al único superadmin activo",
        )
