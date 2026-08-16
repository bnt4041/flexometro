"""Alta de usuarios de una organización.

Crea el usuario en Keycloak con una contraseña temporal (a cambiar en el
primer login) y le envía un correo de bienvenida con el SMTP propio de la
plataforma. El envío de correo es best-effort: si falla, el usuario ya
existe en Keycloak igualmente y queda un "reenviar invitación" aparte —
nunca se guarda la contraseña temporal en la base de datos, así que reenviar
genera una nueva y la sustituye en Keycloak en vez de recordar la anterior.

Desde la Fase 12, un usuario nuevo NO recibe el rol `admin` por defecto —
solo `usuario`, el mínimo para entrar. Qué puede hacer dentro de la
organización lo deciden los grupos a los que se le añada (ver
`permisos_service.py`), no un rol de Keycloak; `admin` sigue existiendo para
quien deba tener acceso total sin depender de grupos, como el primer usuario
de una organización nueva.

Desde la Fase 13, el personal de la propia plataforma (rol `superadmin`) ya
NO se crea desde aquí: pertenecer a una organización y tener acceso a
Administración sobre todas las demás eran dos cosas mezcladas sin razón. Ver
`personal_plataforma_service.py`.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.keycloak_admin import KeycloakAdminClient
from app.core.mailer import MailerError, enviar_correo
from app.core.secretos import generar_password_temporal
from app.modules.core import correo, settings_service
from app.modules.core.models import Organization

ROL_USUARIO = "usuario"
ROL_ADMIN_ORGANIZACION = "admin"


async def _enviar_bienvenida(
    session: AsyncSession,
    *,
    nombre: str,
    organizacion: Organization,
    username: str,
    email: str,
    password_temporal: str,
) -> bool:
    settings = get_settings()
    config_smtp = await settings_service.obtener_configuracion_smtp_plataforma(session)
    cuerpo = correo.render_bienvenida(
        nombre=nombre,
        organizacion_nombre=organizacion.name,
        username=username,
        password_temporal=password_temporal,
        url_app=settings.frontend_url,
    )
    try:
        await enviar_correo(
            config_smtp, destinatario=email, asunto="Tu acceso a Flexómetro", cuerpo_html=cuerpo
        )
        return True
    except MailerError:
        return False


async def crear_usuario_administrador(
    session: AsyncSession,
    organizacion: Organization,
    *,
    username: str,
    email: str,
    nombre: str,
    apellidos: str,
    es_admin: bool = False,
) -> tuple[str, bool]:
    """Devuelve (keycloak_user_id, email_enviado)."""
    settings = get_settings()
    password_temporal = generar_password_temporal()

    roles = [ROL_USUARIO]
    if es_admin:
        roles.append(ROL_ADMIN_ORGANIZACION)

    cliente_kc = KeycloakAdminClient(settings)
    user_id = await cliente_kc.crear_usuario(
        username=username,
        email=email,
        nombre=nombre,
        apellidos=apellidos,
        organizacion_slug=organizacion.slug,
        password_temporal=password_temporal,
        roles=roles,
    )

    email_enviado = await _enviar_bienvenida(
        session,
        nombre=nombre,
        organizacion=organizacion,
        username=username,
        email=email,
        password_temporal=password_temporal,
    )
    return user_id, email_enviado


async def reenviar_bienvenida(
    session: AsyncSession,
    organizacion: Organization,
    *,
    keycloak_user_id: str,
    username: str,
    email: str,
    nombre: str,
) -> bool:
    settings = get_settings()
    password_temporal = generar_password_temporal()
    cliente_kc = KeycloakAdminClient(settings)
    await cliente_kc.resetear_password(keycloak_user_id, password_temporal)

    return await _enviar_bienvenida(
        session,
        nombre=nombre,
        organizacion=organizacion,
        username=username,
        email=email,
        password_temporal=password_temporal,
    )
