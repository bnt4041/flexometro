"""Bandeja de notificaciones, y la aceptación de una solicitud de precios que
llega desde OTRA cuenta.

La parte delicada es `aceptar_solicitud`: cruza la frontera entre dos
organizaciones que además son de cuentas distintas, cosa que hasta ahora el
sistema no hacía. `presupuestos/versionado.py::copiar()` copia entre empresas,
pero solo **dentro de la misma cuenta**, y además deja el ContextVar de
`tenancy` apuntando al origen — la trampa que documenta en sus líneas 409-413.

Aquí se siguen las dos reglas que hacen falta para no repetirla:

1. **Leer TODO lo del emisor antes de mover el contexto.** En cuanto
   `app.organization_id` apunta al destino, RLS deja de enseñar esas filas.
2. **Escribir siempre en la organización propia**, sin tocar el contexto de la
   request: el usuario que acepta ya está autenticado en su organización, así
   que no hay que fijar nada — solo hay que leer lo ajeno con cuidado y volver.

`presupuestos.presupuesto` NO es maestro compartido, y no debe serlo: los
documentos operativos están atados a un CIF concreto. Por eso esto es una
COPIA hacia la organización del proveedor, nunca visibilidad compartida.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import fijar_organizacion_activa
from app.core.tenancy import (
    datos_autoria,
    require_organization_id,
    require_principal,
    reset_organization_id,
    set_organization_id,
)
from app.modules.compras.models import (
    AccesoToken,
    OfertaLinea,
    SolicitudDestinatario,
    SolicitudLinea,
    SolicitudPrecios,
)
from app.modules.compras import oferta_service
from app.modules.compras.publico_acceso import hashear_token
from app.modules.core.models import Notificacion
from app.modules.presupuestos import presupuesto_service
from app.modules.presupuestos.models_presupuesto import (
    EstadoPresupuesto,
    Partida,
    Presupuesto,
    TipoPresupuesto,
)
from app.modules.presupuestos.presupuesto_schemas import (
    CapituloCreate,
    LineaMedicionCreate,
    PartidaCreate,
)

TIPO_SOLICITUD_PRECIOS = "solicitud_precios"


@asynccontextmanager
async def _en_la_organizacion(session: AsyncSession, destino: uuid.UUID):
    """Cruza a otra organización para un tramo acotado, y vuelve pase lo que
    pase. Es el único sitio del módulo donde se cruza, a propósito.

    Hace tres cosas, y las tres hacen falta:

    1. **Vacía lo pendiente ANTES de cruzar.** Los objetos creados en mi
       organización (y las filas de auditoría que arrastran) se escriben en el
       siguiente `flush`; si ese flush cae ya al otro lado, RLS los rechaza
       por `WITH CHECK`. Es un fallo que solo aparece cuando dos operaciones
       comparten transacción, así que conviene cerrarlo aquí y no confiar en
       que nunca pase.
    2. **Mueve la variable de PostgreSQL**, que es lo que ve RLS.
    3. **Mueve también el ContextVar de `tenancy`**, que es de donde
       `cerrar_oferta` saca la organización para numerar y para escribir el
       presupuesto-oferta. Moviendo solo la primera, la numeración usaría la
       serie de la empresa equivocada — la trampa que documenta
       `presupuestos/versionado.py`.
    """
    origen = require_organization_id()
    await session.flush()
    await fijar_organizacion_activa(session, destino)
    token = set_organization_id(destino)
    try:
        yield
    finally:
        await session.flush()
        reset_organization_id(token)
        await fijar_organizacion_activa(session, origen)


class NotificacionNoEncontrada(Exception):
    pass


class NotificacionSinAccion(Exception):
    pass


class SolicitudNoDisponible(Exception):
    pass


async def crear(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    tipo: str,
    titulo: str,
    cuerpo: str | None = None,
    enlace: str | None = None,
    importante: bool = False,
    token_acceso: str | None = None,
    destinatario_subject: str | None = None,
) -> Notificacion:
    """Crea el aviso en la organización que se le diga.

    `organization_id` es explícito y no sale del contexto a propósito: el caso
    que importa es justo el contrario, avisar a una organización que NO es la
    de quien está ejecutando (el emisor avisando al proveedor).
    """
    notificacion = Notificacion(
        organization_id=organization_id,
        tipo=tipo,
        titulo=titulo,
        cuerpo=cuerpo,
        enlace=enlace,
        importante=importante,
        token_acceso=token_acceso,
        destinatario_subject=destinatario_subject,
    )
    session.add(notificacion)
    await session.flush()
    return notificacion


async def listar(
    session: AsyncSession, *, solo_pendientes: bool = False, limite: int = 50
) -> list[Notificacion]:
    """Las de mi organización dirigidas a mí o a todos. RLS ya acota la
    organización; el filtro por `subject` es el que separa lo mío de lo de un
    compañero."""
    subject = require_principal().subject
    consulta = select(Notificacion).where(
        (Notificacion.destinatario_subject.is_(None))
        | (Notificacion.destinatario_subject == subject)
    )
    if solo_pendientes:
        consulta = consulta.where(Notificacion.leida_en.is_(None))
    consulta = consulta.order_by(Notificacion.created_at.desc()).limit(limite)
    return list((await session.execute(consulta)).scalars())


async def contar_pendientes(session: AsyncSession) -> int:
    subject = require_principal().subject
    return (
        await session.scalar(
            select(func.count(Notificacion.id)).where(
                Notificacion.leida_en.is_(None),
                (Notificacion.destinatario_subject.is_(None))
                | (Notificacion.destinatario_subject == subject),
            )
        )
    ) or 0


async def por_presupuesto(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> Notificacion | None:
    """La solicitud de la que salió este presupuesto, si salió de una.

    Es lo que permite ofrecer «Enviar mi oferta» desde la propia ficha del
    presupuesto, que es donde se está trabajando, en vez de obligar a volver a
    buscar el aviso en la campana."""
    return await session.scalar(
        select(Notificacion).where(
            Notificacion.presupuesto_id == presupuesto_id,
            Notificacion.tipo == TIPO_SOLICITUD_PRECIOS,
        )
    )


async def obtener(session: AsyncSession, notificacion_id: uuid.UUID) -> Notificacion:
    notificacion = await session.scalar(
        select(Notificacion).where(Notificacion.id == notificacion_id)
    )
    if notificacion is None:
        raise NotificacionNoEncontrada("Notificación no encontrada")
    return notificacion


async def marcar_leidas(session: AsyncSession, ids: list[uuid.UUID]) -> int:
    """Devuelve cuántas ha marcado. RLS impide tocar las de otra organización,
    así que basta con filtrar por id."""
    if not ids:
        return 0
    ahora = datetime.now(UTC)
    filas = list(
        (
            await session.execute(
                select(Notificacion).where(
                    Notificacion.id.in_(ids), Notificacion.leida_en.is_(None)
                )
            )
        ).scalars()
    )
    for fila in filas:
        fila.leida_en = ahora
    await session.flush()
    return len(filas)


async def _leer_solicitud_ajena(session: AsyncSession, token: str) -> dict:
    """Todo lo que hace falta del lado del EMISOR, leído de una vez y
    devuelto como datos planos.

    Se lee entero antes de volver a mi organización: en cuanto el contexto
    cambia, RLS deja de enseñar estas filas. Es exactamente la regla que
    documenta `versionado.copiar()`.
    """
    # `acceso_token` está fuera de RLS a propósito (es lo único que puede
    # resolver una organización sin contexto), así que esta lectura funciona
    # desde aquí.
    acceso = await session.scalar(
        select(AccesoToken).where(AccesoToken.token_hash == hashear_token(token))
    )
    if acceso is None:
        raise SolicitudNoDisponible("Ese enlace ya no es válido")

    org_emisor = acceso.organization_id
    async with _en_la_organizacion(session, org_emisor):
        destinatario = await session.scalar(
            select(SolicitudDestinatario).where(
                SolicitudDestinatario.id == acceso.destinatario_id
            )
        )
        if destinatario is None:
            raise SolicitudNoDisponible("Ese enlace ya no es válido")
        solicitud = await session.scalar(
            select(SolicitudPrecios).where(SolicitudPrecios.id == destinatario.solicitud_id)
        )
        if solicitud is None:
            raise SolicitudNoDisponible("Ese enlace ya no es válido")

        lineas = [
            {
                "linea_id": str(l.id),
                "capitulo": l.capitulo_resumen or "Sin capítulo",
                "resumen": l.resumen,
                "texto": l.texto,
                "unidad": l.unidad,
                "medicion": l.medicion,
            }
            for l in (
                await session.execute(
                    select(SolicitudLinea)
                    .where(SolicitudLinea.solicitud_id == solicitud.id)
                    .order_by(SolicitudLinea.orden)
                )
            ).scalars()
        ]
        emisor = await session.scalar(
            text("SELECT name FROM core.organization WHERE id = :o"), {"o": str(org_emisor)}
        )
        presupuesto = await session.scalar(
            select(Presupuesto).where(Presupuesto.id == solicitud.presupuesto_id)
        )
        datos = {
            "titulo": solicitud.titulo,
            "codigo": solicitud.codigo,
            "notas": solicitud.notas,
            "emisor": emisor or "",
            "obra": presupuesto.nombre if presupuesto else "",
            "emplazamiento": presupuesto.emplazamiento if presupuesto else None,
            "lineas": lineas,
        }

    if not datos["lineas"]:
        raise SolicitudNoDisponible("Esa solicitud ya no tiene partidas")
    return datos


async def aceptar_solicitud(
    session: AsyncSession, notificacion: Notificacion
) -> Presupuesto:
    """Convierte la solicitud en un presupuesto MÍO, en mi organización.

    Idempotente: si ya se aceptó, devuelve el que se creó, sin duplicar ni
    quemar otro número de serie.
    """
    if notificacion.tipo != TIPO_SOLICITUD_PRECIOS or not notificacion.token_acceso:
        raise NotificacionSinAccion("Esta notificación no es una solicitud de precios")

    if notificacion.presupuesto_id is not None:
        existente = await session.scalar(
            select(Presupuesto).where(Presupuesto.id == notificacion.presupuesto_id)
        )
        if existente is not None:
            return existente

    datos = await _leer_solicitud_ajena(session, notificacion.token_acceso)

    org_id = require_organization_id()
    principal = require_principal()

    # `siguiente_codigo` toma la organización del contexto, que aquí ya es la
    # mía — no hace falta pasarla a mano como en `versionado.copiar()`, porque
    # nunca hemos movido el ContextVar.
    presupuesto = Presupuesto(
        organization_id=org_id,
        codigo=await presupuesto_service.siguiente_codigo(session),
        nombre=f"{datos['titulo']} — {datos['emisor']}",
        descripcion=(
            f"Solicitud de precios {datos['codigo']} de {datos['emisor']}"
            + (f" · Obra: {datos['obra']}" if datos["obra"] else "")
            + (f" · {datos['emplazamiento']}" if datos["emplazamiento"] else "")
        ),
        emplazamiento=datos["emplazamiento"],
        estado=EstadoPresupuesto.BORRADOR,
        tipo=TipoPresupuesto.CLIENTE,
        notas=datos["notas"],
        **datos_autoria(),
    )
    session.add(presupuesto)
    await session.flush()

    por_capitulo: dict[str, list[dict]] = {}
    for linea in datos["lineas"]:
        por_capitulo.setdefault(linea["capitulo"], []).append(linea)

    # El puente para poder devolver la oferta: qué partida MÍA corresponde a
    # qué línea de la solicitud del emisor.
    mapa: dict[str, str] = {}
    for resumen, lineas in por_capitulo.items():
        capitulo = await presupuesto_service.crear_capitulo(
            session, presupuesto.id, CapituloCreate(resumen=resumen)
        )
        assert capitulo is not None
        for linea in lineas:
            partida = await presupuesto_service.crear_partida(
                session,
                capitulo.id,
                PartidaCreate(
                    resumen=linea["resumen"],
                    texto=linea["texto"],
                    unidad=linea["unidad"],
                    precio=None,
                    lineas=[LineaMedicionCreate(uds=linea["medicion"])],
                ),
            )
            if partida is not None:
                mapa[str(partida.id)] = linea["linea_id"]

    notificacion.mapa_lineas = mapa
    notificacion.presupuesto_id = presupuesto.id
    notificacion.resuelta_en = datetime.now(UTC)
    if notificacion.leida_en is None:
        notificacion.leida_en = notificacion.resuelta_en
    await session.flush()
    return presupuesto


class OfertaSinPrecios(Exception):
    pass


async def devolver_oferta(session: AsyncSession, notificacion: Notificacion) -> int:
    """Manda al emisor los precios del presupuesto que el proveedor ha
    preparado, para que entren en su comparativo. Devuelve cuántas líneas.

    Es el camino de vuelta de `aceptar_solicitud`, y cruza la frontera en el
    sentido contrario: se lee TODO lo propio primero y solo después se escribe
    en la organización del emisor, con la variable de PostgreSQL movida a
    propósito para ese tramo y devuelta en un `finally`.

    Deliberadamente NO se mueve el ContextVar de `tenancy`: `cerrar_oferta`
    llama a `siguiente_referencia_libre`, que toma la organización del
    contexto. Si lo moviéramos, el presupuesto-oferta se numeraría con la
    serie de quien está pulsando el botón en vez de la del emisor — que es
    exactamente el error que documenta `versionado.copiar()`.
    """
    if notificacion.presupuesto_id is None or not notificacion.token_acceso:
        raise NotificacionSinAccion("Esta notificación no tiene un presupuesto que devolver")

    if not notificacion.mapa_lineas:
        # Aceptada antes de que existiera el mapa: se reconstruye por
        # descripción, que es lo único que sobrevive a la copia. Con
        # descripciones repetidas puede fallar, así que solo se usa como
        # rescate de lo ya aceptado — las nuevas guardan el mapa al aceptar.
        notificacion.mapa_lineas = await _reconstruir_mapa(session, notificacion)
        await session.flush()

    # --- 1. Todo lo mío, antes de cruzar ---
    precios: dict[str, Decimal] = {}
    for partida in (
        await session.execute(
            select(Partida).where(Partida.presupuesto_id == notificacion.presupuesto_id)
        )
    ).scalars():
        linea_id = (notificacion.mapa_lineas or {}).get(str(partida.id))
        if linea_id and partida.precio is not None and partida.precio > 0:
            precios[linea_id] = partida.precio
    if not precios:
        raise OfertaSinPrecios(
            "Pon precio a alguna partida antes de devolver la oferta"
        )

    acceso = await session.scalar(
        select(AccesoToken).where(
            AccesoToken.token_hash == hashear_token(notificacion.token_acceso)
        )
    )
    if acceso is None:
        raise SolicitudNoDisponible("Esa solicitud ya no existe")

    # --- 2. Escribir en la del emisor, y volver pase lo que pase ---
    async with _en_la_organizacion(session, acceso.organization_id):
        destinatario = await session.scalar(
            select(SolicitudDestinatario).where(
                SolicitudDestinatario.id == acceso.destinatario_id
            )
        )
        if destinatario is None:
            raise SolicitudNoDisponible("Esa solicitud ya no existe")
        solicitud = await session.scalar(
            select(SolicitudPrecios).where(SolicitudPrecios.id == destinatario.solicitud_id)
        )
        if solicitud is None:
            raise SolicitudNoDisponible("Esa solicitud ya no existe")

        # Las líneas se releen acotadas a ESA solicitud: los ids salen de mi
        # mapa y no valen por sí solos.
        validas = {
            str(l.id)
            for l in (
                await session.execute(
                    select(SolicitudLinea).where(SolicitudLinea.solicitud_id == solicitud.id)
                )
            ).scalars()
        }
        ofertas = {
            o.linea_id: o
            for o in (
                await session.execute(
                    select(OfertaLinea).where(OfertaLinea.destinatario_id == destinatario.id)
                )
            ).scalars()
        }

        escritas = 0
        for linea_id, precio in precios.items():
            if linea_id not in validas:
                continue
            clave = uuid.UUID(linea_id)
            oferta = ofertas.get(clave)
            if oferta is None:
                oferta = OfertaLinea(
                    organization_id=acceso.organization_id,
                    destinatario_id=destinatario.id,
                    linea_id=clave,
                )
                session.add(oferta)
                ofertas[clave] = oferta
            oferta.precio_ofertado = precio
            escritas += 1
        await session.flush()

        proveedor_nombre = await session.scalar(
            text("SELECT razon_social FROM terceros.tercero WHERE id = :id"),
            {"id": str(destinatario.proveedor_id)},
        )
        await oferta_service.cerrar_oferta(
            session, solicitud, destinatario, proveedor_nombre=proveedor_nombre or "proveedor"
        )

    notificacion.enviada_en = datetime.now(UTC)
    await session.flush()
    return escritas


async def _reconstruir_mapa(session: AsyncSession, notificacion: Notificacion) -> dict[str, str]:
    """Rescate para notificaciones aceptadas antes de que se guardara el mapa.

    Empareja por descripción: es lo único que se copia tal cual de la línea de
    la solicitud a la partida. Las que no casen se quedan fuera y habrá que
    ponerles precio desde el enlace de siempre.
    """
    if notificacion.presupuesto_id is None or not notificacion.token_acceso:
        return {}

    mias = {
        p.resumen: str(p.id)
        for p in (
            await session.execute(
                select(Partida).where(Partida.presupuesto_id == notificacion.presupuesto_id)
            )
        ).scalars()
    }
    if not mias:
        return {}

    acceso = await session.scalar(
        select(AccesoToken).where(
            AccesoToken.token_hash == hashear_token(notificacion.token_acceso)
        )
    )
    if acceso is None:
        return {}

    mapa: dict[str, str] = {}
    async with _en_la_organizacion(session, acceso.organization_id):
        destinatario = await session.scalar(
            select(SolicitudDestinatario).where(
                SolicitudDestinatario.id == acceso.destinatario_id
            )
        )
        if destinatario is None:
            return mapa
        for linea in (
            await session.execute(
                select(SolicitudLinea).where(
                    SolicitudLinea.solicitud_id == destinatario.solicitud_id
                )
            )
        ).scalars():
            partida_id = mias.get(linea.resumen)
            if partida_id:
                mapa[partida_id] = str(linea.id)
    return mapa
