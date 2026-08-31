"""Alta de flujos y las tres formas de dispararlos."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.core.enlaces import generar_token, hashear_token
from app.core.tenancy import require_organization_id
from app.modules.automatizaciones import motor
from app.modules.automatizaciones.models import Automatizacion, Ejecucion

logger = logging.getLogger(__name__)


class FlujoInvalido(Exception):
    pass


def _resumen_disparador(definicion: dict) -> tuple[str | None, int | None]:
    """El evento y el periodo que declara el disparador, sacados del JSON.

    Se copian a columnas para no tener que abrir el JSON de TODOS los flujos
    cada vez que ocurre un hecho."""
    inicio = motor.disparador_de(definicion)
    if inicio is None:
        return None, None
    parametros = inicio.get("parametros") or {}
    if inicio.get("tipo") == "disparador.evento":
        return (parametros.get("evento") or None), None
    if inicio.get("tipo") == "disparador.programado":
        try:
            return None, max(1, int(parametros.get("cada_minutos") or 60))
        except (TypeError, ValueError):
            return None, 60
    return None, None


async def listar(session: AsyncSession) -> list[Automatizacion]:
    return list(
        await session.scalars(
            select(Automatizacion)
            .where(Automatizacion.organization_id == require_organization_id())
            .order_by(Automatizacion.nombre)
        )
    )


async def obtener(session: AsyncSession, flujo_id: uuid.UUID) -> Automatizacion | None:
    return await session.scalar(
        select(Automatizacion).where(
            Automatizacion.id == flujo_id,
            Automatizacion.organization_id == require_organization_id(),
        )
    )


async def guardar(
    session: AsyncSession,
    flujo: Automatizacion | None,
    *,
    nombre: str,
    descripcion: str | None,
    definicion: dict,
    activa: bool,
    autoria: dict | None = None,
) -> tuple[Automatizacion, str | None]:
    """Crea o actualiza. Devuelve `(flujo, token_en_claro_si_es_nuevo)`.

    Activar un flujo con problemas se rechaza; guardarlo a medias, no. Montar
    un flujo lleva varias sentadas y bloquear el guardado obligaría a
    terminarlo de una vez."""
    problemas = motor.validar(definicion)
    if activa and problemas:
        raise FlujoInvalido(" ".join(problemas))

    evento, minutos = _resumen_disparador(definicion)
    inicio = motor.disparador_de(definicion)
    es_webhook = inicio is not None and inicio.get("tipo") == "disparador.webhook"

    token_claro = None
    if flujo is None:
        flujo = Automatizacion(
            organization_id=require_organization_id(), nombre=nombre, **(autoria or {})
        )
        session.add(flujo)

    flujo.nombre = nombre
    flujo.descripcion = descripcion
    flujo.definicion = definicion
    flujo.activa = activa
    flujo.evento_disparador = evento
    flujo.proxima_ejecucion_en = (
        datetime.now(UTC) + timedelta(minutes=minutos) if (minutos and activa) else None
    )

    # El token del webhook se genera una sola vez y no se regenera al
    # guardar: si cambiara, el sistema que ya llama a esa URL dejaría de
    # funcionar sin que nadie tocara nada.
    if es_webhook and flujo.token_hash is None:
        token_claro, flujo.token_hash = generar_token()
    elif not es_webhook:
        flujo.token_hash = None

    await session.flush()
    return flujo, token_claro


async def borrar(session: AsyncSession, flujo: Automatizacion) -> None:
    await session.delete(flujo)
    await session.flush()


# ── Disparadores ────────────────────────────────────────────────────────


async def disparar_por_evento(
    session: AsyncSession, codigo: str, *, organization_id: uuid.UUID, datos: dict
) -> int:
    """Arranca los flujos activos que escuchan ese evento.

    NUNCA lanza: es un efecto lateral del hecho, igual que un aviso o un
    webhook. Que un flujo falle no puede tumbar la firma que lo provocó."""
    try:
        flujos = list(
            await session.scalars(
                select(Automatizacion).where(
                    Automatizacion.organization_id == organization_id,
                    Automatizacion.activa.is_(True),
                    Automatizacion.evento_disparador == codigo,
                )
            )
        )
        for flujo in flujos:
            await motor.ejecutar(session, flujo, disparador=codigo, entrada=datos)
        return len(flujos)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron disparar flujos de «%s»: %s", codigo, exc)
        return 0


async def por_token(session: AsyncSession, token: str) -> Automatizacion | None:
    """El flujo de un token de webhook. Solo se guarda el hash, así que se
    busca por él — nunca por el token en claro."""
    return await session.scalar(
        select(Automatizacion).where(
            Automatizacion.token_hash == hashear_token(token),
            Automatizacion.activa.is_(True),
        )
    )


#: Igual que los otros dos trabajos de fondo, con su propia llave para poder
#: correr a la vez que ellos.
_LOCK = 815_213_006
INTERVALO_SEGUNDOS = 60


async def pasada_programada() -> int:
    """Los flujos con reloj a los que ya les toca."""
    lanzados = 0
    async with SessionFactory() as session:
        conseguido = await session.scalar(
            text("SELECT pg_try_advisory_lock(:clave)"), {"clave": _LOCK}
        )
        if not conseguido:
            return 0
        try:
            ahora = datetime.now(UTC)
            flujos = list(
                await session.scalars(
                    select(Automatizacion).where(
                        Automatizacion.activa.is_(True),
                        Automatizacion.proxima_ejecucion_en.is_not(None),
                        Automatizacion.proxima_ejecucion_en <= ahora,
                    )
                )
            )
            for flujo in flujos:
                await session.execute(
                    text("SELECT set_config('app.organization_id', :o, true)"),
                    {"o": str(flujo.organization_id)},
                )
                _, minutos = _resumen_disparador(flujo.definicion or {})
                # La próxima se calcula ANTES de ejecutar: si la pasada tarda
                # o revienta, el flujo no se queda atascado repitiéndose.
                flujo.proxima_ejecucion_en = ahora + timedelta(minutes=minutos or 60)
                await session.flush()
                await motor.ejecutar(
                    session, flujo, disparador="programado", entrada={"momento": ahora.isoformat()}
                )
                lanzados += 1
            await session.commit()
        finally:
            await session.execute(
                text("SELECT pg_advisory_unlock(:clave)"), {"clave": _LOCK}
            )
    return lanzados


async def bucle() -> None:
    import asyncio

    while True:
        try:
            await pasada_programada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallo lanzando flujos programados: %s", exc)
        await asyncio.sleep(INTERVALO_SEGUNDOS)


async def ejecuciones_de(
    session: AsyncSession, flujo_id: uuid.UUID, limite: int = 30
) -> list[Ejecucion]:
    return list(
        await session.scalars(
            select(Ejecucion)
            .where(Ejecucion.automatizacion_id == flujo_id)
            .order_by(Ejecucion.created_at.desc())
            .limit(min(limite, 100))
        )
    )
