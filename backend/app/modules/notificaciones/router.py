import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos as catalogo
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.modules.notificaciones import suscripciones_service
from app.modules.notificaciones.schemas import (
    PreferenciaIn,
    PreferenciaOut,
    SuscripcionIn,
    SuscripcionOut,
    TipoEventoOut,
)

# `/api/avisos` y no `/api/notificaciones`: ese espacio ya lo ocupa la BANDEJA
# (la campana, en `core`). Son cosas distintas —una es la lista de lo que te
# ha llegado, esto es la configuración de qué llega— y compartir prefijo solo
# lleva a confundirlas al leer las rutas.
router = APIRouter(
    prefix="/api/avisos",
    tags=["notificaciones"],
    dependencies=[Depends(require_module("notificaciones"))],
)


@router.get("/eventos", response_model=list[TipoEventoOut])
async def listar_eventos(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[TipoEventoOut]:
    """El catálogo, filtrado a los módulos que esta organización tiene
    encendidos: ofrecer avisos de facturación a quien no factura sería
    configurar algo que no puede pasar."""
    from app.modules.core.service import active_module_codes

    activos = await active_module_codes(session, principal.organization_id)
    return [
        TipoEventoOut(
            codigo=e.codigo,
            modulo=e.modulo,
            etiqueta=e.etiqueta,
            descripcion=e.descripcion,
            disparador=e.disparador,
            parametros=[p.__dict__ for p in e.parametros],
        )
        for e in catalogo.catalogo()
        if e.modulo in activos
    ]


@router.get("/suscripciones", response_model=list[SuscripcionOut])
async def listar_suscripciones(
    usuario_subject: str | None = None,
    grupo_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("notificaciones", "ver")),
) -> list[SuscripcionOut]:
    filas = await suscripciones_service.listar(
        session, usuario_subject=usuario_subject, grupo_id=grupo_id
    )
    return [SuscripcionOut.model_validate(f) for f in filas]


@router.put("/suscripciones", response_model=SuscripcionOut | None)
async def guardar_suscripcion(
    datos: SuscripcionIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("notificaciones", "editar")),
) -> SuscripcionOut | None:
    """Crea, actualiza o borra la suscripción de un destinatario a un evento.

    Es un PUT sobre la pareja (destinatario, evento) y no un POST con id
    porque eso es lo que hay en pantalla: una casilla por evento en la ficha
    de alguien. Sin canales, se borra y devuelve `null`."""
    try:
        suscripcion = await suscripciones_service.guardar(
            session,
            tipo_evento=datos.tipo_evento,
            usuario_subject=datos.usuario_subject,
            grupo_id=datos.grupo_id,
            canales=datos.canales,
            parametros=datos.parametros,
            activa=datos.activa,
        )
    except suscripciones_service.SuscripcionInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return SuscripcionOut.model_validate(suscripcion) if suscripcion else None


# ── Preferencias de una persona ─────────────────────────────────────────
# Solo su móvil y el silencio: qué recibe y por dónde son suscripciones.


@router.get("/usuarios/{subject}/preferencias", response_model=PreferenciaOut)
async def preferencias_de(
    subject: str,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("notificaciones", "ver")),
) -> PreferenciaOut:
    return PreferenciaOut.model_validate(
        await suscripciones_service.preferencia_de(session, subject)
    )


@router.put("/usuarios/{subject}/preferencias", response_model=PreferenciaOut)
async def guardar_preferencias_de(
    subject: str,
    datos: PreferenciaIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("notificaciones", "editar")),
) -> PreferenciaOut:
    preferencia = await suscripciones_service.preferencia_de(session, subject)
    preferencia.telefono = datos.telefono
    preferencia.silenciado = datos.silenciado
    await session.flush()
    return PreferenciaOut.model_validate(preferencia)


# ── Lo de uno mismo ─────────────────────────────────────────────────────
# Sin `require_permiso`: son SUS ajustes. Pedir permiso de módulo para
# silenciar tus propios avisos dejaría fuera justo a quien solo los recibe.


@router.get("/mis-preferencias", response_model=PreferenciaOut)
async def mis_preferencias(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> PreferenciaOut:
    return PreferenciaOut.model_validate(
        await suscripciones_service.preferencia_de(session, principal.subject)
    )


@router.put("/mis-preferencias", response_model=PreferenciaOut)
async def guardar_mis_preferencias(
    datos: PreferenciaIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> PreferenciaOut:
    preferencia = await suscripciones_service.preferencia_de(session, principal.subject)
    preferencia.telefono = datos.telefono
    preferencia.silenciado = datos.silenciado
    await session.flush()
    return PreferenciaOut.model_validate(preferencia)
