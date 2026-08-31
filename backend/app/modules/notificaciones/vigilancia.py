"""El latido que revisa las vigilancias.

Una vigilancia avisa de que NO ha pasado nada («esta obra lleva tres meses
parada»), así que no hay ningún momento en el que dispararse: hay que ir a
mirar cada cierto tiempo.

Va dentro del proceso de la API y no en un contenedor aparte para no añadir
una pieza más al stack por una consulta cada hora. Lo que sí hace falta es
que solo UNA instancia lo ejecute aunque haya varias levantadas, y eso lo
resuelve un advisory lock de Postgres: quien no lo consigue, no hace nada y
vuelve a intentarlo a la siguiente. Es la misma base de datos que ya
comparten, así que no hace falta coordinar nada más.
"""

import asyncio
import json
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos as catalogo
from app.core.database import SessionFactory
from app.modules.notificaciones import service
from app.modules.notificaciones.models import AvisoEmitido, SuscripcionAviso

logger = logging.getLogger(__name__)

#: Cada cuánto se mira. Las vigilancias hablan de días, así que una hora es
#: de sobra fina y no castiga la base de datos.
INTERVALO_SEGUNDOS = 3600

#: Número arbitrario pero fijo: identifica ESTE trabajo entre los advisory
#: locks de la base. Cambiarlo permitiría que dos versiones corrieran a la vez.
_LOCK = 815_213_004


async def evaluar_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> int:
    """Pasa todas las vigilancias activas de una organización. Devuelve
    cuántos avisos nuevos ha soltado.

    Las suscripciones se agrupan por evento Y plazo: veinte personas
    suscritas a «obras paradas 90 días» son UNA consulta, no veinte. Lo que
    sí es por suscripción es la memoria de lo ya avisado, para que quien se
    suscriba hoy se entere de lo que YA está pasando."""
    suscripciones = list(
        await session.scalars(
            select(SuscripcionAviso).where(
                SuscripcionAviso.organization_id == organization_id,
                SuscripcionAviso.activa.is_(True),
            )
        )
    )

    # (evento, parámetros) -> suscripciones que comparten esa búsqueda.
    grupos: dict[tuple[str, str], list[SuscripcionAviso]] = {}
    for suscripcion in suscripciones:
        evento = catalogo.obtener(suscripcion.tipo_evento)
        if evento is None or evento.disparador is not catalogo.Disparador.VIGILANCIA:
            continue
        clave_grupo = (
            suscripcion.tipo_evento,
            json.dumps(suscripcion.parametros or {}, sort_keys=True),
        )
        grupos.setdefault(clave_grupo, []).append(suscripcion)

    nuevos = 0
    for (codigo, parametros_json), suscritas in grupos.items():
        buscador = catalogo.buscador_de(codigo)
        if buscador is None:
            continue
        try:
            candidatos = await buscador(
                session, organization_id, json.loads(parametros_json)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vigilancia «%s» falló: %s", codigo, exc)
            continue
        if not candidatos:
            continue

        ya = {
            suscripcion.id: set(
                await session.scalars(
                    select(AvisoEmitido.clave).where(
                        AvisoEmitido.suscripcion_id == suscripcion.id
                    )
                )
            )
            for suscripcion in suscritas
        }

        for clave, titulo, cuerpo, enlace in candidatos:
            pendientes = [s for s in suscritas if clave not in ya[s.id]]
            if not pendientes:
                continue
            await service.entregar(
                session,
                pendientes,
                organization_id=organization_id,
                codigo=codigo,
                titulo=titulo,
                cuerpo=cuerpo,
                enlace=enlace,
            )
            # Se anota aunque no haya llegado a nadie: si una suscripción no
            # alcanza a nadie válido, repetir la búsqueda cada hora no lo
            # arregla y solo gasta.
            for suscripcion in pendientes:
                session.add(
                    AvisoEmitido(
                        organization_id=organization_id,
                        suscripcion_id=suscripcion.id,
                        clave=clave,
                    )
                )
            nuevos += 1
        await session.flush()
    return nuevos


async def pasada() -> int:
    """Una vuelta completa por las organizaciones que tengan suscripciones."""
    total = 0
    async with SessionFactory() as session:
        conseguido = await session.scalar(
            text("SELECT pg_try_advisory_lock(:clave)"), {"clave": _LOCK}
        )
        if not conseguido:
            logger.debug("Otra instancia está evaluando las vigilancias")
            return 0
        try:
            organizaciones = list(
                await session.scalars(
                    select(SuscripcionAviso.organization_id)
                    .where(SuscripcionAviso.activa.is_(True))
                    .distinct()
                )
            )
            for organization_id in organizaciones:
                # Cada organización en su propio ámbito de RLS, igual que una
                # petición suya.
                await session.execute(
                    text("SELECT set_config('app.organization_id', :o, true)"),
                    {"o": str(organization_id)},
                )
                total += await evaluar_organizacion(session, organization_id)
            await session.commit()
        finally:
            await session.execute(
                text("SELECT pg_advisory_unlock(:clave)"), {"clave": _LOCK}
            )
    if total:
        logger.info("Vigilancias: %s aviso(s) nuevo(s)", total)
    return total


async def bucle() -> None:
    """Tarea de fondo. Se cancela al apagar la aplicación."""
    while True:
        try:
            await pasada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Nunca muere: un fallo puntual (base caída al arrancar) no puede
            # dejar la aplicación sin vigilancias hasta el siguiente reinicio.
            logger.warning("Fallo evaluando vigilancias: %s", exc)
        await asyncio.sleep(INTERVALO_SEGUNDOS)
