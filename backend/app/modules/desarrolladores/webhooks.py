"""Avisar a sistemas de fuera cuando pasa algo.

Mismo catálogo de eventos que las notificaciones (`app/core/eventos.py`): es
el mismo hecho contado a otro público.

Lo que separa un webhook de una llamada HTTP suelta son tres cosas, y las
tres están aquí:

1. **Se encola, no se manda.** Publicar dentro de la transacción que provocó
   el hecho ataría el guardado de una factura a que el servidor de otro esté
   vivo. Se guarda la entrega y se reparte aparte.
2. **Va firmada.** Sin firma, cualquiera que adivine la URL puede inventarse
   eventos. La firma es HMAC-SHA256 sobre `timestamp.cuerpo`, y el timestamp
   entra dentro para que una copia capturada no valga mañana.
3. **Se reintenta con espera creciente.** Un 500 pasajero no puede perder el
   aviso; insistir cada segundo tampoco ayuda a quien está caído.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.modules.desarrolladores.enums import EstadoEntrega
from app.modules.desarrolladores.models import EntregaWebhook, SuscripcionWebhook

logger = logging.getLogger(__name__)

#: Espera antes de cada reintento. Seis intentos que abarcan algo más de dos
#: horas: cubre un reinicio o un despliegue del otro lado sin insistir tanto
#: que parezca un ataque.
ESPERAS = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10),
           timedelta(minutes=30), timedelta(hours=2))
MAX_INTENTOS = len(ESPERAS) + 1

_TIEMPO_ESPERA = 15.0
#: Igual que el del evaluador de vigilancias: uno distinto para que los dos
#: trabajos puedan correr a la vez.
_LOCK = 815_213_005
INTERVALO_SEGUNDOS = 60


def firmar(secreto: str, cuerpo: bytes, momento: int) -> str:
    """`t=<epoch>,v1=<hmac>` — el mismo formato que usa Stripe, porque quien
    integre esto probablemente ya lo haya implementado una vez."""
    firma = hmac.new(
        secreto.encode(), f"{momento}.".encode() + cuerpo, hashlib.sha256
    ).hexdigest()
    return f"t={momento},v1={firma}"


async def encolar(
    session: AsyncSession,
    codigo: str,
    *,
    organization_id: uuid.UUID,
    datos: dict,
) -> int:
    """Deja una entrega preparada por cada suscripción interesada.

    NUNCA lanza: un webhook es un efecto lateral del hecho, no el hecho.
    """
    try:
        suscripciones = list(
            await session.scalars(
                select(SuscripcionWebhook).where(
                    SuscripcionWebhook.organization_id == organization_id,
                    SuscripcionWebhook.activa.is_(True),
                )
            )
        )
        creadas = 0
        for suscripcion in suscripciones:
            if codigo not in (suscripcion.eventos or []):
                continue
            session.add(
                EntregaWebhook(
                    organization_id=organization_id,
                    suscripcion_id=suscripcion.id,
                    evento=codigo,
                    payload={
                        "evento": codigo,
                        "ocurrido_en": datetime.now(UTC).isoformat(),
                        "organizacion": str(organization_id),
                        "datos": datos,
                    },
                    estado=EstadoEntrega.PENDIENTE,
                    proximo_intento_en=datetime.now(UTC),
                )
            )
            creadas += 1
        await session.flush()
        return creadas
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudieron encolar webhooks de «%s»: %s", codigo, exc)
        return 0


async def _entregar(
    cliente: httpx.AsyncClient, entrega: EntregaWebhook, suscripcion: SuscripcionWebhook
) -> None:
    """Un intento. Deja la entrega con su resultado, sin lanzar."""
    # `separators` sin espacios y `sort_keys`: el cuerpo firmado y el enviado
    # tienen que ser el MISMO byte a byte, o la firma no valida al otro lado.
    cuerpo = json.dumps(
        entrega.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    momento = int(datetime.now(UTC).timestamp())

    entrega.intentos += 1
    try:
        respuesta = await cliente.post(
            suscripcion.url,
            content=cuerpo,
            headers={
                "Content-Type": "application/json",
                "X-Flexometro-Firma": firmar(suscripcion.secreto, cuerpo, momento),
                "X-Flexometro-Evento": entrega.evento,
                "X-Flexometro-Entrega": str(entrega.id),
            },
        )
    except httpx.HTTPError as exc:
        entrega.error = str(exc)[:500]
        entrega.respuesta_codigo = None
    else:
        entrega.respuesta_codigo = respuesta.status_code
        if respuesta.status_code < 300:
            entrega.estado = EstadoEntrega.ENTREGADA
            entrega.entregada_en = datetime.now(UTC)
            entrega.proximo_intento_en = None
            entrega.error = None
            return
        entrega.error = respuesta.text[:500]

    if entrega.intentos >= MAX_INTENTOS:
        entrega.estado = EstadoEntrega.AGOTADA
        entrega.proximo_intento_en = None
    else:
        entrega.estado = EstadoEntrega.FALLIDA
        entrega.proximo_intento_en = datetime.now(UTC) + ESPERAS[entrega.intentos - 1]


async def repartir(limite: int = 50) -> int:
    """Manda lo pendiente que ya toca. Devuelve cuántas entregas se movieron."""
    movidas = 0
    async with SessionFactory() as session:
        conseguido = await session.scalar(
            text("SELECT pg_try_advisory_lock(:clave)"), {"clave": _LOCK}
        )
        if not conseguido:
            return 0
        try:
            ahora = datetime.now(UTC)
            pendientes = list(
                await session.scalars(
                    select(EntregaWebhook)
                    .where(
                        EntregaWebhook.estado.in_(
                            [EstadoEntrega.PENDIENTE, EstadoEntrega.FALLIDA]
                        ),
                        EntregaWebhook.proximo_intento_en <= ahora,
                    )
                    .order_by(EntregaWebhook.proximo_intento_en)
                    .limit(limite)
                )
            )
            if not pendientes:
                return 0

            async with httpx.AsyncClient(timeout=_TIEMPO_ESPERA, follow_redirects=False) as cliente:
                for entrega in pendientes:
                    suscripcion = await session.get(SuscripcionWebhook, entrega.suscripcion_id)
                    if suscripcion is None or not suscripcion.activa:
                        # La suscripción se apagó mientras esto esperaba:
                        # mandar ahora sería avisar a quien ya dijo que no.
                        entrega.estado = EstadoEntrega.AGOTADA
                        entrega.proximo_intento_en = None
                        entrega.error = "La suscripción ya no está activa"
                        movidas += 1
                        continue
                    await _entregar(cliente, entrega, suscripcion)
                    movidas += 1
            await session.commit()
        finally:
            await session.execute(
                text("SELECT pg_advisory_unlock(:clave)"), {"clave": _LOCK}
            )
    return movidas


async def bucle() -> None:
    """Tarea de fondo. Se cancela al apagar la aplicación."""
    while True:
        try:
            await repartir()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallo repartiendo webhooks: %s", exc)
        await asyncio.sleep(INTERVALO_SEGUNDOS)
