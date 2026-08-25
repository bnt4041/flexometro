"""Alta, edición y envío de un paquete de solicitud de precios.

Un paquete ("Yeserías") define QUÉ se pide una sola vez, en `SolicitudLinea`,
y se manda a tantos proveedores como haga falta — cada uno un
`SolicitudDestinatario`, con su enlace, su estado y su presupuesto-oferta.

Lo que se guarda en `SolicitudLinea` es una COPIA CONGELADA de la partida (o
de un componente de su descompuesto), no una referencia viva: si el
presupuesto se edita después, lo que los proveedores están cotizando no puede
cambiarles bajo los pies. `partida_id`/`concepto_id` quedan como rastro para
poder volcar después la oferta sobre la partida correcta.

Las líneas del paquete son editables SIEMPRE, también después de enviarlo
(decisión explícita del usuario): quien envía decide si reenvía a los
proveedores anteriores, y se acepta que el comparativo tenga huecos donde
alguien no haya cotizado algo.

Crear y enviar son dos pasos separados, y enviar es POR DESTINATARIO: el
token de acceso de un proveedor no se genera hasta que se le manda a él, así
que mientras el paquete es un borrador no hay ningún enlace vivo.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mailer import MailerError, enviar_correo
from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import datos_autoria, require_organization_id, require_principal
from app.modules.compras.models import (
    AccesoEstado,
    AccesoToken,
    EstadoDestinatario,
    EstadoSolicitud,
    OfertaLinea,
    SolicitudDestinatario,
    SolicitudLinea,
    SolicitudPrecios,
)
from app.modules.compras.publico_acceso import generar_token
from app.modules.core import correo
from app.modules.core.settings_service import configuracion_smtp_de
from app.modules.presupuestos import presupuesto_service
from app.modules.presupuestos.models_presupuesto import Capitulo, Partida, Presupuesto
from app.modules.terceros.models import Tercero

TIPO_DOCUMENTO = "solicitud_precios"

# Cuánto vive el enlace si no se pone fecha límite. Corto a propósito: el
# token viaja en una URL de correo, que es reenviable y queda en historiales
# y logs de proxy.
DIAS_VALIDEZ_POR_DEFECTO = 30


class PresupuestoInvalido(Exception):
    pass


class ProveedorInvalido(Exception):
    pass


class SinPartidas(Exception):
    pass


class DestinatarioNoEditable(Exception):
    """El proveedor ya recibió el paquete (o ya contestó): quitarlo de la
    lista se llevaría por delante su oferta."""

    pass


class SinCorreoDeProveedor(Exception):
    """No es un fallo del envío: es que no hay a dónde mandarlo. Se distingue
    de `MailerError` para poder ofrecer «Copiar enlace» como alternativa en
    vez de un 502 genérico."""

    pass


# Estados en los que todavía tiene sentido emitir un enlace para el proveedor
# (los mismos que `publico_acceso._ESTADOS_ABIERTOS` acepta, más el borrador,
# que al emitirlo pasa a enviada).
_ESTADOS_CON_ENLACE = frozenset(
    {
        EstadoDestinatario.BORRADOR,
        EstadoDestinatario.ENVIADA,
        EstadoDestinatario.RESPONDIDA,
    }
)


async def _codigo_libre(session: AsyncSession) -> str:
    org_id = require_organization_id()

    async def existe(codigo: str) -> bool:
        encontrado = await session.scalar(
            select(SolicitudPrecios.id).where(
                SolicitudPrecios.organization_id == org_id,
                SolicitudPrecios.codigo == codigo,
            )
        )
        return encontrado is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento=TIPO_DOCUMENTO, existe=existe
    )


async def _partidas_validas(
    session: AsyncSession, *, presupuesto_id: uuid.UUID, partida_ids: list[uuid.UUID]
) -> list[tuple[Partida, str]]:
    """Partida + resumen de su capítulo, acotado SIEMPRE a presupuesto y
    organización: los ids llegan del cliente y no se pueden dar por buenos."""
    if not partida_ids:
        return []
    org_id = require_organization_id()
    filas = (
        await session.execute(
            select(Partida, Capitulo.resumen)
            .join(Capitulo, Capitulo.id == Partida.capitulo_id)
            .where(
                Partida.id.in_(partida_ids),
                Partida.presupuesto_id == presupuesto_id,
                Partida.organization_id == org_id,
            )
            .order_by(Capitulo.orden, Partida.orden)
        )
    ).all()
    return list(filas)


async def _resolver_lineas(
    session: AsyncSession,
    *,
    presupuesto_id: uuid.UUID,
    partida_ids: list[uuid.UUID],
    componentes: list[tuple[uuid.UUID, uuid.UUID]],
) -> list[dict]:
    """Los datos congelados de cada línea pedida, ya validados contra el
    presupuesto. Cada elemento lleva su clave de identidad
    `(partida_id, concepto_id)` — con `concepto_id` a `None` para las partidas
    enteras.

    Una partida entera y un componente suyo pueden convivir en la misma
    solicitud: son preguntas distintas al proveedor ("¿cuánto por ejecutar
    esto?" frente a "¿cuánto me cuesta este material?").
    """
    resueltas: list[dict] = []

    for partida, capitulo_resumen in await _partidas_validas(
        session, presupuesto_id=presupuesto_id, partida_ids=partida_ids
    ):
        resueltas.append(
            {
                "partida_id": partida.id,
                "concepto_id": None,
                "capitulo_resumen": capitulo_resumen,
                "codigo": partida.codigo,
                "resumen": partida.resumen,
                "texto": partida.texto,
                "unidad": partida.unidad,
                "medicion": partida.medicion,
            }
        )

    # Los componentes se agrupan por partida para leer el descompuesto una vez
    # cada una. `descomposicion_de_partida` ya resuelve tanto el descompuesto
    # propio como el heredado del banco, que es justo lo que aquí hace falta:
    # se puede pedir precio de un componente sin tener que independizar antes.
    por_partida: dict[uuid.UUID, set[uuid.UUID]] = {}
    for partida_id, concepto_id in componentes:
        por_partida.setdefault(partida_id, set()).add(concepto_id)

    for partida_id, conceptos in por_partida.items():
        validas = await _partidas_validas(
            session, presupuesto_id=presupuesto_id, partida_ids=[partida_id]
        )
        if not validas:
            continue
        partida, capitulo_resumen = validas[0]
        resultado = await presupuesto_service.descomposicion_de_partida(session, partida.id)
        if resultado is None:
            continue
        for linea in resultado[1]:
            if linea["hijo_id"] not in conceptos:
                continue
            resueltas.append(
                {
                    "partida_id": partida.id,
                    "concepto_id": linea["hijo_id"],
                    # El capítulo pierde protagonismo: al proveedor le importa
                    # de qué partida sale este material o esta mano de obra.
                    "capitulo_resumen": f"{capitulo_resumen} · {partida.resumen}"[:250],
                    "codigo": linea["codigo"],
                    "resumen": linea["resumen"],
                    "texto": None,
                    "unidad": linea["unidad"],
                    # Lo que hay que comprar de verdad: el rendimiento es por
                    # unidad de partida, así que se multiplica por su medición.
                    "medicion": (
                        linea["rendimiento"] * linea["factor"] * partida.medicion
                    ).quantize(Decimal("0.001")),
                }
            )

    return resueltas


async def _proveedor_valido(session: AsyncSession, proveedor_id: uuid.UUID) -> Tercero:
    org_id = require_organization_id()
    proveedor = await session.scalar(
        select(Tercero).where(Tercero.id == proveedor_id, Tercero.organization_id == org_id)
    )
    if proveedor is None:
        raise ProveedorInvalido("El proveedor no existe en esta organización")
    if not proveedor.es_proveedor:
        raise ProveedorInvalido(f"«{proveedor.razon_social}» no está marcado como proveedor")
    return proveedor


async def crear_solicitud(
    session: AsyncSession,
    *,
    presupuesto_id: uuid.UUID,
    titulo: str,
    proveedor_ids: list[uuid.UUID],
    partida_ids: list[uuid.UUID],
    componentes: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
    fecha_limite: date | None = None,
    notas: str | None = None,
) -> SolicitudPrecios:
    """Deja el paquete en `BORRADOR`, con un destinatario por proveedor. No
    genera ningún acceso ni manda nada — eso es cosa de `enviar_a`, un paso
    aparte, explícito y por destinatario."""
    org_id = require_organization_id()

    presupuesto = await session.scalar(
        select(Presupuesto).where(
            Presupuesto.id == presupuesto_id, Presupuesto.organization_id == org_id
        )
    )
    if presupuesto is None:
        raise PresupuestoInvalido("El presupuesto no existe en esta organización")

    proveedores = [await _proveedor_valido(session, pid) for pid in proveedor_ids]

    resueltas = await _resolver_lineas(
        session,
        presupuesto_id=presupuesto_id,
        partida_ids=partida_ids,
        componentes=componentes or [],
    )
    if not resueltas:
        raise SinPartidas("No hay ninguna partida válida en la selección")

    principal = require_principal()
    solicitud = SolicitudPrecios(
        organization_id=org_id,
        codigo=await _codigo_libre(session),
        titulo=titulo,
        presupuesto_id=presupuesto_id,
        estado=EstadoSolicitud.BORRADOR,
        fecha_limite=fecha_limite,
        notas=notas,
        emisor_subject=principal.subject,
        emisor_nombre=principal.username,
        **datos_autoria(),
    )
    session.add(solicitud)
    await session.flush()

    for orden, datos in enumerate(resueltas):
        session.add(
            SolicitudLinea(
                organization_id=org_id, solicitud_id=solicitud.id, orden=orden, **datos
            )
        )
    for proveedor in proveedores:
        session.add(
            SolicitudDestinatario(
                organization_id=org_id,
                solicitud_id=solicitud.id,
                proveedor_id=proveedor.id,
                estado=EstadoDestinatario.BORRADOR,
            )
        )
    await session.flush()
    return solicitud


async def anadir_destinatario(
    session: AsyncSession,
    solicitud: SolicitudPrecios,
    proveedor_id: uuid.UUID,
    email_destino: str | None = None,
) -> SolicitudDestinatario:
    """Un proveedor más al paquete, también cuando ya se envió a otros:
    recibe exactamente las mismas líneas."""
    proveedor = await _proveedor_valido(session, proveedor_id)
    ya_esta = await session.scalar(
        select(SolicitudDestinatario).where(
            SolicitudDestinatario.solicitud_id == solicitud.id,
            SolicitudDestinatario.proveedor_id == proveedor.id,
        )
    )
    if ya_esta is not None:
        raise ProveedorInvalido(f"«{proveedor.razon_social}» ya está en esta solicitud")

    destinatario = SolicitudDestinatario(
        organization_id=require_organization_id(),
        solicitud_id=solicitud.id,
        proveedor_id=proveedor.id,
        email_destino=email_destino,
        estado=EstadoDestinatario.BORRADOR,
    )
    session.add(destinatario)
    await session.flush()
    return destinatario


async def quitar_destinatario(
    session: AsyncSession, destinatario: SolicitudDestinatario
) -> None:
    """Solo mientras no haya salido: si ya tiene enlace o ha contestado,
    quitarlo se llevaría por delante su oferta y su acceso."""
    if destinatario.estado != EstadoDestinatario.BORRADOR:
        raise DestinatarioNoEditable(
            "Este proveedor ya recibió la solicitud: no se puede quitar de la lista"
        )
    await session.delete(destinatario)
    await session.flush()


async def actualizar_lineas(
    session: AsyncSession,
    solicitud: SolicitudPrecios,
    partida_ids: list[uuid.UUID],
    componentes: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> None:
    """Añade/quita líneas del paquete, **también después de enviarlo**.

    Diferencial por `(partida_id, concepto_id)`: las que se mantienen no se
    tocan, así que las ofertas ya recibidas sobre ellas sobreviven intactas;
    las que salen se llevan sus `OfertaLinea` por cascada, que es lo correcto
    (si la línea ya no se pide, su precio no significa nada).

    Añadir una línea a un paquete ya enviado la deja pendiente para todos:
    quien ya contestó simplemente no la tiene ofertada, y sale como hueco en
    el comparativo hasta que se le reenvíe y la rellene."""
    resueltas = await _resolver_lineas(
        session,
        presupuesto_id=solicitud.presupuesto_id,
        partida_ids=partida_ids,
        componentes=componentes or [],
    )
    if not resueltas:
        raise SinPartidas("No hay ninguna partida válida en la selección")

    actuales = (
        await session.execute(
            select(SolicitudLinea).where(SolicitudLinea.solicitud_id == solicitud.id)
        )
    ).scalars().all()
    existentes = {(l.partida_id, l.concepto_id) for l in actuales}
    pedidas = {(d["partida_id"], d["concepto_id"]) for d in resueltas}

    for linea in actuales:
        if (linea.partida_id, linea.concepto_id) not in pedidas:
            await session.delete(linea)

    org_id = require_organization_id()
    orden_base = len(existentes)
    for orden, datos in enumerate(resueltas):
        if (datos["partida_id"], datos["concepto_id"]) in existentes:
            continue
        session.add(
            SolicitudLinea(
                organization_id=org_id,
                solicitud_id=solicitud.id,
                orden=orden_base + orden,
                **datos,
            )
        )
    await session.flush()


async def actualizar_datos(
    session: AsyncSession, solicitud: SolicitudPrecios, cambios: dict
) -> None:
    """`cambios` es un `SolicitudActualizar.model_dump(exclude_unset=True)`:
    solo toca lo que el cliente mandó explícitamente. Sin guard de estado, por
    el mismo motivo que `actualizar_lineas`: el paquete se retoca cuando haga
    falta y quien envía decide si reenvía."""
    for campo, valor in cambios.items():
        setattr(solicitud, campo, valor)
    await session.flush()


async def eliminar_borrador(session: AsyncSession, solicitud: SolicitudPrecios) -> None:
    """Solo mientras no haya salido a nadie: borrar un paquete ya enviado se
    llevaría por delante ofertas que los proveedores han rellenado."""
    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise DestinatarioNoEditable(
            "Este paquete ya se envió: no se puede eliminar sin perder las ofertas recibidas"
        )
    await session.delete(solicitud)
    await session.flush()


async def _emitir_acceso(
    session: AsyncSession, destinatario: SolicitudDestinatario, *, fecha_limite: date | None
) -> str:
    """Crea el acceso de UN proveedor y devuelve la URL EN CLARO, que es la
    única vez que existe: en base de datos solo queda el hash.

    Emitir invalida su acceso anterior — no se puede "recuperar" el enlace ya
    mandado (por diseño, ver `publico_acceso.py`), así que pedir uno nuevo
    necesariamente jubila al viejo. Lo que el proveedor ya hubiera rellenado
    NO se pierde: vive en `OfertaLinea`, colgado del destinatario, no del
    token.
    """
    org_id = require_organization_id()

    anteriores = (
        await session.execute(
            select(AccesoToken).where(AccesoToken.destinatario_id == destinatario.id)
        )
    ).scalars().all()
    for anterior in anteriores:
        await session.delete(anterior)
    await session.flush()

    token, token_hash = generar_token()
    session.add(
        AccesoToken(
            organization_id=org_id, token_hash=token_hash, destinatario_id=destinatario.id
        )
    )

    caduca = datetime.now(UTC) + timedelta(days=DIAS_VALIDEZ_POR_DEFECTO)
    if fecha_limite is not None:
        # Margen sobre la fecha límite: que el enlace no muera justo el día
        # que el proveedor iba a contestar.
        limite = datetime.combine(
            fecha_limite, datetime.min.time(), tzinfo=UTC
        ) + timedelta(days=7)
        caduca = max(caduca, limite)

    estado = await session.scalar(
        select(AccesoEstado).where(AccesoEstado.destinatario_id == destinatario.id)
    )
    if estado is None:
        session.add(
            AccesoEstado(
                organization_id=org_id, destinatario_id=destinatario.id, expira_en=caduca
            )
        )
    else:
        # El estado (usos, revocado…) es del DESTINATARIO, no del token: se
        # reutiliza la fila y solo se reabre la ventana de validez.
        estado.expira_en = caduca
        estado.revocado = False
    await session.flush()

    return f"{get_settings().frontend_url.rstrip('/')}/oferta/{token}"


def _marcar_enviado(solicitud: SolicitudPrecios, destinatario: SolicitudDestinatario) -> None:
    """Un destinatario que sale por primera vez pasa a `enviada`; si ya había
    contestado se queda como está (reenviarle no borra su respuesta). El
    paquete pasa a `enviada` en cuanto sale al primero."""
    if destinatario.estado == EstadoDestinatario.BORRADOR:
        destinatario.estado = EstadoDestinatario.ENVIADA
    if destinatario.enviada_en is None:
        destinatario.enviada_en = datetime.now(UTC)
    if solicitud.estado == EstadoSolicitud.BORRADOR:
        solicitud.estado = EstadoSolicitud.ENVIADA


async def enviar_a(
    session: AsyncSession, solicitud: SolicitudPrecios, destinatario: SolicitudDestinatario
) -> str:
    """Manda el paquete a UN proveedor y devuelve su URL, para poder ofrecer
    "copiar enlace" justo después sin emitir otro (que invalidaría el recién
    mandado).

    Sirve igual para el primer envío y para reenviar tras haber retocado las
    líneas: emite un enlace nuevo, el anterior muere, y lo que ese proveedor
    ya hubiera rellenado se conserva.

    Deja que `MailerError` se propague — igual que en el resto de la
    aplicación, el envío es best-effort y quien llama decide si sigue
    adelante o avisa."""
    org_id = require_organization_id()

    presupuesto = await session.scalar(
        select(Presupuesto).where(Presupuesto.id == solicitud.presupuesto_id)
    )
    proveedor = await session.scalar(
        select(Tercero).where(Tercero.id == destinatario.proveedor_id)
    )
    # `email_destino` manda sobre la ficha del proveedor: es el correo elegido
    # para ESTE destinatario (el comercial que lo lleva, la dirección de
    # ofertas…).
    correo_destino = destinatario.email_destino or (proveedor.email if proveedor else None)
    if not correo_destino:
        raise SinCorreoDeProveedor(
            "No hay a dónde mandarlo: escribe un correo de envío para este proveedor, "
            "añade el email en su ficha, o usa «Copiar enlace» y pásaselo tú."
        )
    total_lineas = len(
        (
            await session.execute(
                select(SolicitudLinea.id).where(SolicitudLinea.solicitud_id == solicitud.id)
            )
        ).all()
    )

    emisor_nombre = await session.scalar(
        text("SELECT name FROM core.organization WHERE id = :org"), {"org": str(org_id)}
    )

    url = await _emitir_acceso(session, destinatario, fecha_limite=solicitud.fecha_limite)

    cuerpo = correo.render_solicitud_precios(
        emisor_nombre=emisor_nombre or "",
        proveedor_nombre=proveedor.razon_social if proveedor else None,
        presupuesto_nombre=presupuesto.nombre if presupuesto else "",
        titulo=solicitud.titulo,
        emplazamiento=presupuesto.emplazamiento if presupuesto else None,
        num_lineas=total_lineas,
        notas=solicitud.notas,
        fecha_limite=solicitud.fecha_limite.isoformat() if solicitud.fecha_limite else None,
        url_oferta=url,
    )

    config = await configuracion_smtp_de(session, org_id)
    await enviar_correo(
        config,
        destinatario=correo_destino,
        asunto=f"Solicitud de precios — {solicitud.titulo}",
        cuerpo_html=cuerpo,
    )

    _marcar_enviado(solicitud, destinatario)
    await session.flush()
    return url


async def generar_enlace(
    session: AsyncSession, solicitud: SolicitudPrecios, destinatario: SolicitudDestinatario
) -> str:
    """Enlace para pasárselo al proveedor por el medio que sea (WhatsApp, un
    correo escrito a mano…) en vez de mandarlo desde aquí.

    Emite uno NUEVO cada vez, y el anterior deja de funcionar: el token solo
    se guarda hasheado, así que no hay forma de volver a enseñar el que ya se
    mandó."""
    if destinatario.estado not in _ESTADOS_CON_ENLACE:
        raise DestinatarioNoEditable("Este proveedor ya está cerrado")

    url = await _emitir_acceso(session, destinatario, fecha_limite=solicitud.fecha_limite)
    _marcar_enviado(solicitud, destinatario)
    await session.flush()
    return url


async def obtener_destinatario(
    session: AsyncSession, destinatario_id: uuid.UUID
) -> SolicitudDestinatario | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(SolicitudDestinatario).where(
            SolicitudDestinatario.id == destinatario_id,
            SolicitudDestinatario.organization_id == org_id,
        )
    )


async def listar_por_presupuesto(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[SolicitudPrecios]:
    """Todos los paquetes de este presupuesto (borradores incluidos) — es lo
    que alimenta la pestaña Comparativo."""
    org_id = require_organization_id()
    filas = (
        await session.execute(
            select(SolicitudPrecios)
            .where(
                SolicitudPrecios.presupuesto_id == presupuesto_id,
                SolicitudPrecios.organization_id == org_id,
            )
            .order_by(SolicitudPrecios.codigo)
        )
    ).scalars()
    return list(filas)


async def obtener_oferta_linea(
    session: AsyncSession, oferta_id: uuid.UUID
) -> "OfertaLinea | None":
    org_id = require_organization_id()
    return await session.scalar(
        select(OfertaLinea).where(
            OfertaLinea.id == oferta_id, OfertaLinea.organization_id == org_id
        )
    )


async def obtener_solicitud(
    session: AsyncSession, solicitud_id: uuid.UUID
) -> SolicitudPrecios | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(SolicitudPrecios).where(
            SolicitudPrecios.id == solicitud_id, SolicitudPrecios.organization_id == org_id
        )
    )


async def obtener_linea(
    session: AsyncSession, linea_id: uuid.UUID
) -> SolicitudLinea | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(SolicitudLinea).where(
            SolicitudLinea.id == linea_id, SolicitudLinea.organization_id == org_id
        )
    )
