"""Alta de personal de la plataforma (Flexómetro) — Fase 13.

A diferencia de `usuarios_service.py`, no hay ninguna `Organization` de por
medio: el rol `superadmin` desbloquea la sección de Administración para
CUALQUIER organización precisamente porque no pertenece a ninguna en
particular. Mismo patrón de contraseña temporal + correo de bienvenida
best-effort que el alta de usuarios de organización.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ROL_SUPERADMIN
from app.core.config import get_settings
from app.core.keycloak_admin import KeycloakAdminClient
from app.core.mailer import MailerError, enviar_correo
from app.core.secretos import generar_password_temporal
from app.modules.core import correo, settings_service


async def _enviar_bienvenida_plataforma(
    session: AsyncSession,
    *,
    nombre: str,
    username: str,
    email: str,
    password_temporal: str,
) -> bool:
    settings = get_settings()
    config_smtp = await settings_service.obtener_configuracion_smtp_plataforma(session)
    cuerpo = correo.render_bienvenida(
        nombre=nombre,
        username=username,
        password_temporal=password_temporal,
        url_app=settings.frontend_url,
        es_plataforma=True,
    )
    try:
        await enviar_correo(
            config_smtp, destinatario=email, asunto="Tu acceso a Flexómetro", cuerpo_html=cuerpo
        )
        return True
    except MailerError:
        return False


async def crear_usuario_plataforma(
    session: AsyncSession,
    *,
    username: str,
    email: str,
    nombre: str,
    apellidos: str,
) -> tuple[str, bool]:
    """Devuelve (keycloak_user_id, email_enviado)."""
    settings = get_settings()
    password_temporal = generar_password_temporal()

    cliente_kc = KeycloakAdminClient(settings)
    user_id = await cliente_kc.crear_usuario(
        username=username,
        email=email,
        nombre=nombre,
        apellidos=apellidos,
        organizacion_slug=None,
        password_temporal=password_temporal,
        roles=[ROL_SUPERADMIN],
    )

    email_enviado = await _enviar_bienvenida_plataforma(
        session, nombre=nombre, username=username, email=email, password_temporal=password_temporal
    )
    return user_id, email_enviado


async def reenviar_bienvenida_plataforma(
    session: AsyncSession,
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

    return await _enviar_bienvenida_plataforma(
        session, nombre=nombre, username=username, email=email, password_temporal=password_temporal
    )
