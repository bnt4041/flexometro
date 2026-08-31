"""Repartir avisos: quién los recibe y por dónde.

El camino completo:

    algo pasa  ->  emitir()  ->  suscripciones activas de ese evento
                              ->  personas (usuarios + miembros de grupos)
                              ->  filtro de permisos
                              ->  campana / correo / WhatsApp

El filtro de permisos va antes de entregar nada y no es cortesía: el título
de un aviso lleva nombres de cliente e importes. Avisar a quien no puede
abrir el registro sería enseñarle por la campana lo que la pantalla le niega.
"""

import logging
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos as catalogo
from app.core.enums import Alcance
from app.core.mensajeria import Canal, Destinatario, Mensaje, MensajeriaError, proveedor_de
from app.core.permisos import permiso_de_usuario
from app.modules.notificaciones.models import PreferenciaUsuario, SuscripcionAviso

logger = logging.getLogger(__name__)

#: La bandeja de la aplicación. No es un canal de mensajería —no sale a
#: ningún sitio, es una fila en una tabla— así que no vive en `Canal`.
CAMPANA = "campana"

CANALES_POSIBLES = (CAMPANA, Canal.EMAIL.value, Canal.WHATSAPP.value)


async def suscripciones_de_evento(
    session: AsyncSession, organization_id: uuid.UUID, codigo: str
) -> list[SuscripcionAviso]:
    return list(
        await session.scalars(
            select(SuscripcionAviso).where(
                SuscripcionAviso.organization_id == organization_id,
                SuscripcionAviso.tipo_evento == codigo,
                SuscripcionAviso.activa.is_(True),
            )
        )
    )


async def personas_de(
    session: AsyncSession, suscripcion: SuscripcionAviso
) -> set[str]:
    """Los `subject` a los que alcanza una suscripción, resuelto el grupo."""
    from app.modules.core.permisos_models import GrupoUsuario

    if suscripcion.usuario_subject:
        return {suscripcion.usuario_subject}
    if not suscripcion.grupo_id:
        return set()
    miembros = await session.scalars(
        select(GrupoUsuario.usuario_subject).where(
            GrupoUsuario.organization_id == suscripcion.organization_id,
            GrupoUsuario.grupo_id == suscripcion.grupo_id,
        )
    )
    return set(miembros)


async def entregar(
    session: AsyncSession,
    suscripciones: Iterable[SuscripcionAviso],
    *,
    organization_id: uuid.UUID,
    codigo: str,
    titulo: str,
    cuerpo: str | None = None,
    enlace: str | None = None,
    importante: bool = False,
) -> int:
    """Reparte UN aviso entre las personas de esas suscripciones. Devuelve a
    cuántas llegó.

    Una persona puede salir de varias suscripciones a la vez (por su grupo y
    por su nombre): se unen los canales en vez de mandarle lo mismo dos veces.
    """
    evento = catalogo.obtener(codigo)
    if evento is None:
        logger.warning("Evento «%s» sin registrar en el catálogo", codigo)
        return 0

    por_persona: dict[str, set[str]] = {}
    for suscripcion in suscripciones:
        canales = {c for c in (suscripcion.canales or []) if c in CANALES_POSIBLES}
        if not canales:
            continue
        for subject in await personas_de(session, suscripcion):
            por_persona.setdefault(subject, set()).update(canales)

    avisados = 0
    for subject, canales in por_persona.items():
        permitidos = await _canales_permitidos(
            session, organization_id, subject, evento.modulo, canales
        )
        if not permitidos:
            continue
        await _entregar_a(
            session,
            organization_id=organization_id,
            subject=subject,
            canales=permitidos,
            codigo=codigo,
            titulo=titulo,
            cuerpo=cuerpo,
            enlace=enlace,
            importante=importante,
        )
        avisados += 1
    return avisados


async def emitir(
    session: AsyncSession,
    codigo: str,
    *,
    organization_id: uuid.UUID,
    titulo: str,
    cuerpo: str | None = None,
    enlace: str | None = None,
    importante: bool = False,
) -> int:
    """Lo que llama el código cuando pasa algo.

    NUNCA lanza. Un aviso es un efecto lateral de otra cosa que sí importa
    (firmar, facturar); que falle el correo no puede tumbar la operación que
    lo provocó.
    """
    try:
        # Los sistemas de fuera se enteran del hecho aunque no haya nadie
        # suscrito a él: son dos públicos independientes, y hacer que uno
        # dependa del otro sería una sorpresa desagradable el día que alguien
        # quite la última suscripción de personas.
        from app.modules.desarrolladores.webhooks import encolar

        await encolar(
            session,
            codigo,
            organization_id=organization_id,
            datos={"titulo": titulo, "cuerpo": cuerpo, "enlace": enlace},
        )

        # Y los flujos que escuchen este evento. Tercer público del mismo
        # hecho: personas, sistemas de fuera y automatizaciones.
        from app.modules.automatizaciones.service import disparar_por_evento

        await disparar_por_evento(
            session,
            codigo,
            organization_id=organization_id,
            datos={"titulo": titulo, "cuerpo": cuerpo, "enlace": enlace},
        )

        suscripciones = await suscripciones_de_evento(session, organization_id, codigo)
        if not suscripciones:
            return 0
        return await entregar(
            session, suscripciones,
            organization_id=organization_id, codigo=codigo, titulo=titulo,
            cuerpo=cuerpo, enlace=enlace, importante=importante,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo avisar de «%s»: %s", codigo, exc)
        return 0


async def _canales_permitidos(
    session: AsyncSession,
    organization_id: uuid.UUID,
    subject: str,
    modulo: str,
    canales: set[str],
) -> set[str]:
    permiso = await permiso_de_usuario(
        session, organization_id=organization_id, subject=subject, module_code=modulo
    )
    if permiso.ver == Alcance.NINGUNO:
        logger.info(
            "No se avisa a %s de un evento de «%s»: no tiene permiso de verlo", subject, modulo
        )
        return set()

    preferencia = await session.scalar(
        select(PreferenciaUsuario).where(
            PreferenciaUsuario.organization_id == organization_id,
            PreferenciaUsuario.usuario_subject == subject,
        )
    )
    if preferencia is not None and preferencia.silenciado:
        # La campana se sigue llenando: silenciar es no querer que te
        # interrumpan, no dejar de enterarte.
        return canales & {CAMPANA}
    return canales


async def _entregar_a(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject: str,
    canales: set[str],
    codigo: str,
    titulo: str,
    cuerpo: str | None,
    enlace: str | None,
    importante: bool,
) -> None:
    if CAMPANA in canales:
        from app.modules.core import notificaciones_service

        await notificaciones_service.crear(
            session,
            organization_id=organization_id,
            tipo=codigo,
            titulo=titulo,
            cuerpo=cuerpo,
            enlace=enlace,
            importante=importante,
            destinatario_subject=subject,
        )

    salientes = {c for c in canales if c != CAMPANA}
    if not salientes:
        return

    destino = await _direcciones(session, organization_id, subject)
    if destino is None:
        logger.info("Sin dirección conocida para %s: solo campana", subject)
        return

    mensaje = Mensaje(
        asunto=titulo,
        texto=f"{titulo}\n\n{cuerpo or ''}".strip() + (f"\n\n{enlace}" if enlace else ""),
        html=(
            f"<p><strong>{titulo}</strong></p>"
            + (f"<p>{cuerpo}</p>" if cuerpo else "")
            + (f'<p><a href="{enlace}">Abrir en Flexómetro</a></p>' if enlace else "")
        ),
        variables=(titulo, cuerpo or ""),
    )
    for nombre_canal in salientes:
        canal = Canal(nombre_canal)
        proveedor = await proveedor_de(session, organization_id, canal)
        if proveedor is None or proveedor.direccion_de(destino) is None:
            continue
        try:
            await proveedor.enviar(destino, mensaje)
        except MensajeriaError as exc:
            logger.warning("No se pudo avisar a %s por %s: %s", subject, canal.value, exc)


async def _direcciones(
    session: AsyncSession, organization_id: uuid.UUID, subject: str
) -> Destinatario | None:
    """Correo y móvil de un usuario.

    El correo vive en Keycloak (no hay tabla de usuarios propia) y el móvil en
    su preferencia, porque Keycloak no lo guarda y además es dato suyo.
    """
    from app.modules.core.permisos_models import GrupoUsuario

    nombre = await session.scalar(
        select(GrupoUsuario.usuario_nombre).where(
            GrupoUsuario.organization_id == organization_id,
            GrupoUsuario.usuario_subject == subject,
        )
    )
    preferencia = await session.scalar(
        select(PreferenciaUsuario).where(
            PreferenciaUsuario.organization_id == organization_id,
            PreferenciaUsuario.usuario_subject == subject,
        )
    )

    email = None
    try:
        from app.core.config import get_settings
        from app.core.keycloak_admin import KeycloakAdmin

        email = await KeycloakAdmin(get_settings()).email_de(subject)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer el correo de %s en Keycloak: %s", subject, exc)

    telefono = preferencia.telefono if preferencia else None
    if not email and not telefono:
        return None
    return Destinatario(nombre=nombre or subject, email=email, telefono=telefono)
