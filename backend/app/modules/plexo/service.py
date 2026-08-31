"""El vínculo entre organizaciones: buscarse, invitarse, aceptar o romper.

Nada de esto mueve datos de negocio todavía —eso es la pieza siguiente,
intercambio de documentos— pero la fila del vínculo en sí ya referencia a
dos organizaciones a la vez, que es la parte nueva. Ver el docstring de
`models.py` y la migración para la política RLS que lo permite sin abrir
nada más.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.database import fijar_organizacion_activa
from app.core.tenancy import require_organization_id
from app.modules.core.models import Organization
from app.modules.plexo.enums import EstadoVinculo
from app.modules.plexo.models import Perfil, Vinculo

logger = logging.getLogger(__name__)

TIPO_INVITACION = "plexo_invitacion"
TIPO_RESPUESTA = "plexo_respuesta"


class PlexoError(Exception):
    """Cualquier fallo de negocio de aquí. El router lo traduce a 400."""


# ── Perfil: el interruptor de «que me encuentren» ────────────────────────


async def mi_perfil(session: AsyncSession) -> Perfil:
    org_id = require_organization_id()
    perfil = await session.get(Perfil, org_id)
    if perfil is None:
        # Se crea apagado la primera vez que alguien mira, no al activar el
        # módulo: así el módulo se puede encender para BUSCAR sin que eso ya
        # te haga visible a los demás.
        perfil = Perfil(organization_id=org_id, visible=False)
        session.add(perfil)
        await session.flush()
    return perfil


async def fijar_visibilidad(session: AsyncSession, visible: bool) -> Perfil:
    perfil = await mi_perfil(session)
    if perfil.visible != visible:
        perfil.visible = visible
        perfil.activado_en = datetime.now(UTC) if visible else perfil.activado_en
        await session.flush()
    return perfil


# ── Buscar ────────────────────────────────────────────────────────────────


async def buscar(session: AsyncSession, texto: str, *, limite: int = 20) -> list[Organization]:
    """Organizaciones visibles cuyo nombre o CIF encaja. Nunca la propia."""
    texto = texto.strip()
    if len(texto) < 2:
        return []
    org_id = require_organization_id()
    patron = f"%{texto}%"
    filas = await session.execute(
        select(Organization)
        .join(Perfil, Perfil.organization_id == Organization.id)
        .where(
            Perfil.visible.is_(True),
            Organization.id != org_id,
            or_(Organization.name.ilike(patron), Organization.cif.ilike(patron)),
        )
        .order_by(Organization.name)
        .limit(limite)
    )
    return list(filas.scalars())


# ── Vínculos ────────────────────────────────────────────────────────────


def _es_participante(vinculo: Vinculo, org_id: uuid.UUID) -> bool:
    return org_id in (vinculo.organizacion_origen_id, vinculo.organizacion_destino_id)


async def obtener_vinculo(session: AsyncSession, vinculo_id: uuid.UUID) -> Vinculo | None:
    """La RLS de la tabla ya solo deja ver filas donde participas: no hace
    falta filtrar por organización aquí también."""
    return await session.get(Vinculo, vinculo_id)


async def listar_vinculos(session: AsyncSession, estado: EstadoVinculo | None) -> list[Vinculo]:
    org_id = require_organization_id()
    consulta = select(Vinculo).where(
        or_(Vinculo.organizacion_origen_id == org_id, Vinculo.organizacion_destino_id == org_id)
    )
    if estado is not None:
        consulta = consulta.where(Vinculo.estado == estado)
    filas = await session.execute(consulta.order_by(Vinculo.created_at.desc()))
    return list(filas.scalars())


async def invitar(
    session: AsyncSession, principal: Principal, destino_id: uuid.UUID, mensaje: str | None
) -> Vinculo:
    org_id = require_organization_id()
    if destino_id == org_id:
        raise PlexoError("No te puedes invitar a ti mismo")

    destino = await session.get(Organization, destino_id)
    perfil_destino = await session.get(Perfil, destino_id)
    if destino is None or perfil_destino is None or not perfil_destino.visible:
        # Mismo mensaje exista o no la organización, y esté o no visible: no
        # hay que dejar adivinar por la respuesta qué CIF están registrados
        # en la plataforma.
        raise PlexoError("Esa organización no está en el universo Plexo ahora mismo")

    existente = await session.scalar(
        select(Vinculo).where(
            Vinculo.estado.in_((EstadoVinculo.PENDIENTE, EstadoVinculo.ACEPTADO)),
            or_(
                (Vinculo.organizacion_origen_id == org_id)
                & (Vinculo.organizacion_destino_id == destino_id),
                (Vinculo.organizacion_origen_id == destino_id)
                & (Vinculo.organizacion_destino_id == org_id),
            ),
        )
    )
    if existente is not None:
        raise PlexoError(
            "Ya hay una invitación pendiente o una conexión activa con esta organización"
        )

    vinculo = Vinculo(
        organizacion_origen_id=org_id,
        organizacion_destino_id=destino_id,
        estado=EstadoVinculo.PENDIENTE,
        mensaje=mensaje,
        invitado_por_subject=principal.subject,
        invitado_por_nombre=principal.username,
    )
    session.add(vinculo)
    await session.flush()

    await _avisar(
        session,
        destino_id,
        tipo=TIPO_INVITACION,
        titulo=f"{principal.organization_slug or 'Una organización'} quiere conectar contigo",
        cuerpo=mensaje,
        enlace="/plexo",
    )
    return vinculo


async def aceptar(session: AsyncSession, principal: Principal, vinculo: Vinculo) -> Vinculo:
    org_id = require_organization_id()
    if vinculo.organizacion_destino_id != org_id:
        raise PlexoError("Solo quien recibe la invitación puede aceptarla")
    if vinculo.estado != EstadoVinculo.PENDIENTE:
        raise PlexoError("Esta invitación ya no está pendiente")
    _responder(vinculo, principal, EstadoVinculo.ACEPTADO)
    await session.flush()
    await _avisar(
        session,
        vinculo.organizacion_origen_id,
        tipo=TIPO_RESPUESTA,
        titulo=f"{principal.organization_slug or 'La organización'} ha aceptado tu invitación",
        enlace="/plexo",
    )
    return vinculo


async def rechazar(session: AsyncSession, principal: Principal, vinculo: Vinculo) -> Vinculo:
    org_id = require_organization_id()
    if vinculo.organizacion_destino_id != org_id:
        raise PlexoError("Solo quien recibe la invitación puede rechazarla")
    if vinculo.estado != EstadoVinculo.PENDIENTE:
        raise PlexoError("Esta invitación ya no está pendiente")
    _responder(vinculo, principal, EstadoVinculo.RECHAZADO)
    await session.flush()
    # Un rechazo no se avisa dentro de la aplicación a propósito: es
    # información sensible para quien lo recibe, y no aporta nada accionable
    # a quien invitó salvo saber que le han dicho que no.
    return vinculo


async def revocar(session: AsyncSession, principal: Principal, vinculo: Vinculo) -> Vinculo:
    org_id = require_organization_id()
    if not _es_participante(vinculo, org_id):
        raise PlexoError("No formas parte de este vínculo")
    if vinculo.estado == EstadoVinculo.PENDIENTE and vinculo.organizacion_origen_id != org_id:
        raise PlexoError("Solo quien invitó puede retirar una invitación pendiente")
    if vinculo.estado not in (EstadoVinculo.PENDIENTE, EstadoVinculo.ACEPTADO):
        raise PlexoError("Este vínculo ya está cerrado")

    era_aceptado = vinculo.estado == EstadoVinculo.ACEPTADO
    _responder(vinculo, principal, EstadoVinculo.REVOCADO)
    await session.flush()

    if era_aceptado:
        # Al otro lado sí le interesa saberlo: tenía una conexión activa y
        # deja de tenerla.
        otro = (
            vinculo.organizacion_destino_id
            if org_id == vinculo.organizacion_origen_id
            else vinculo.organizacion_origen_id
        )
        await _avisar(
            session,
            otro,
            tipo=TIPO_RESPUESTA,
            titulo=f"{principal.organization_slug or 'La organización'} ha desconectado del plexo",
            enlace="/plexo",
        )
    return vinculo


def _responder(vinculo: Vinculo, principal: Principal, estado: EstadoVinculo) -> None:
    vinculo.estado = estado
    vinculo.respondido_por_subject = principal.subject
    vinculo.respondido_por_nombre = principal.username
    vinculo.respondido_en = datetime.now(UTC)


async def _avisar(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    tipo: str,
    titulo: str,
    cuerpo: str | None = None,
    enlace: str | None = None,
) -> None:
    """Dejar un aviso en la bandeja de LA OTRA organización.

    Mismo patrón que `compras/solicitud_service.py::avisar_si_tiene_cuenta`:
    se cruza el `SET LOCAL` de Postgres para este INSERT concreto —no el
    ContextVar de `tenancy`, que confundiría a todo lo demás que corre en
    esta request— y se vuelve a la organización propia inmediatamente
    después, pase lo que pase.
    """
    from app.modules.core import notificaciones_service

    propia = require_organization_id()
    await fijar_organizacion_activa(session, organization_id)
    try:
        await notificaciones_service.crear(
            session,
            organization_id=organization_id,
            tipo=tipo,
            titulo=titulo,
            cuerpo=cuerpo,
            enlace=enlace,
            importante=True,
        )
    except Exception:  # noqa: BLE001
        # Un aviso es un efecto lateral: que falle no puede tumbar la
        # invitación o la respuesta que sí importa.
        logger.warning("No se pudo avisar a la organización %s", organization_id, exc_info=True)
    finally:
        await fijar_organizacion_activa(session, propia)
