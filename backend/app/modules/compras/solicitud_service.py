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

import logging
import uuid

import httpx
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import fijar_organizacion_activa
from app.core.keycloak_admin import KeycloakAdminClient, KeycloakAdminError
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
from app.modules.core import notificaciones_service
from app.modules.core.models import Organization
from app.modules.core.settings_service import configuracion_smtp_de
from app.modules.presupuestos import presupuesto_service
from app.modules.presupuestos.models_presupuesto import Capitulo, Partida, Presupuesto
from app.modules.terceros.models import Tercero

logger = logging.getLogger("obras.compras.solicitud")

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
    """Saca a un proveedor de la solicitud, en cualquier estado.

    Se lleva por delante su acceso y lo que hubiera ofertado (por cascada), y
    deja sin adjudicar las líneas que se le hubieran adjudicado — pero NO su
    presupuesto-oferta, que es un documento aparte y se queda en Presupuestos
    de proveedor. Tampoco deshace un precio ya aplicado sobre una partida: eso
    ya está en el presupuesto de cliente y se cambia allí.

    Quien llama debe advertir de lo que se pierde: aquí no se pregunta.
    """
    # `SolicitudLinea.adjudicada_a_id` es SET NULL, así que las líneas
    # adjudicadas a este proveedor se quedan sin adjudicar solas. Se hace
    # explícito para que el comparativo vuelva a ofrecer el botón de adjudicar
    # dentro de la misma transacción, sin depender de recargar.
    for linea in (
        await session.execute(
            select(SolicitudLinea).where(SolicitudLinea.adjudicada_a_id == destinatario.id)
        )
    ).scalars():
        linea.adjudicada_a_id = None

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


async def eliminar(session: AsyncSession, solicitud: SolicitudPrecios) -> None:
    """Borra la solicitud entera, en cualquier estado.

    Por cascada se van sus líneas, sus destinatarios, lo que hubieran ofertado
    y sus enlaces —que dejan de funcionar al momento—. Lo que NO se toca:

    - Los presupuestos-oferta ya generados, que siguen en Presupuestos de
      proveedor: son documentos por derecho propio.
    - Los precios ya adjudicados sobre partidas del presupuesto de cliente:
      eso ya está aplicado y se cambia desde el presupuesto.

    Quien llama debe advertir de lo que se pierde: aquí no se pregunta.
    """
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

    # Si el proveedor ya tiene Flexómetro, el aviso le llega dentro de su
    # aplicación y allí puede convertirlo en un presupuesto suyo.
    en_su_flexometro = await avisar_si_tiene_cuenta(
        session, solicitud, destinatario, url=url, correo_destino=correo_destino
    )
    portada = get_settings().frontend_url.rstrip("/")

    cuerpo = correo.render_solicitud_precios(
        emisor_nombre=emisor_nombre or "",
        proveedor_nombre=proveedor.razon_social if proveedor else None,
        presupuesto_nombre=presupuesto.nombre if presupuesto else "",
        titulo=solicitud.titulo,
        emplazamiento=presupuesto.emplazamiento if presupuesto else None,
        num_lineas=total_lineas,
        notas=solicitud.notas,
        fecha_limite=solicitud.fecha_limite.isoformat() if solicitud.fecha_limite else None,
        # A quien ya tiene Flexómetro no se le manda el enlace externo: sería
        # sacarle de su propia aplicación, donde el aviso ya le espera y donde
        # puede trabajarlo con sus precios. El correo solo avisa.
        url_oferta=None if en_su_flexometro else url,
        url_aplicacion=portada if en_su_flexometro else None,
        # Y a quien NO la tiene, una invitación discreta al pie.
        url_landing=None if en_su_flexometro else portada,
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


async def _organizacion_del_correo(session: AsyncSession, email: str) -> uuid.UUID | None:
    """La organización de Flexómetro de ese correo, si la tiene.

    El directorio de usuarios vive entero en Keycloak (no hay tabla de
    usuarios), así que se pregunta allí. Best-effort a conciencia: si Keycloak
    no contesta, no está configurado, o el correo pertenece a varios usuarios,
    se devuelve `None` y el envío sigue por correo como siempre — que un
    proveedor no reciba la notificación es un incordio, que no le llegue nada
    es un fallo.
    """
    try:
        cliente = KeycloakAdminClient(get_settings())
        usuario = await cliente.buscar_por_email(email)
    except (KeycloakAdminError, httpx.HTTPError) as exc:
        # Que Keycloak no conteste no puede tumbar un envío: se sigue por
        # correo, que es lo que había antes de existir las notificaciones.
        # El `except` es estrecho a propósito: un fallo de programación aquí
        # dentro debe reventar y verse, no quedarse en un aviso silencioso
        # que haga creer que "es que ese proveedor no tiene cuenta".
        logger.warning("No se pudo consultar Keycloak por %s: %s", email, exc)
        return None
    if usuario is None:
        return None

    slugs = (usuario.get("attributes") or {}).get("organizacion") or []
    if isinstance(slugs, str):
        slugs = [s.strip() for s in slugs.split(",") if s.strip()]
    if len(slugs) != 1:
        # Sin organización, o con varias: no hay forma de saber en cuál
        # quiere recibirlo.
        return None

    return await session.scalar(
        select(Organization.id).where(
            Organization.slug == slugs[0], Organization.is_active.is_(True)
        )
    )


async def avisar_si_tiene_cuenta(
    session: AsyncSession,
    solicitud: SolicitudPrecios,
    destinatario: SolicitudDestinatario,
    *,
    url: str,
    correo_destino: str,
) -> bool:
    """Si el proveedor ya tiene Flexómetro, le deja el aviso dentro de SU
    aplicación además del correo. Devuelve si lo ha dejado.

    La notificación se crea en la organización del proveedor, no en la del
    emisor: es su bandeja. Lleva el enlace en claro porque es exactamente lo
    que le habría llegado por correo, y ahí vive protegido por el RLS de su
    propia organización.
    """
    org_proveedor = await _organizacion_del_correo(session, correo_destino)
    # Pedirse precio a uno mismo no tiene sentido y además cruzaría el aviso
    # con el paquete original.
    if org_proveedor is None or org_proveedor == require_organization_id():
        return False

    org_emisor = require_organization_id()
    emisor = await session.scalar(
        text("SELECT name FROM core.organization WHERE id = :o"), {"o": str(org_emisor)}
    )
    token = url.rsplit("/", 1)[-1]

    # La fila va en la organización del PROVEEDOR, y el `WITH CHECK` de su
    # política RLS lo impide mientras el contexto sea el del emisor — que es
    # justo lo que tiene que hacer. Así que se cruza a propósito, para este
    # único INSERT, y se vuelve pase lo que pase.
    #
    # Aquí basta con mover la variable de PostgreSQL y NO el ContextVar de
    # `tenancy`: `crear` recibe la organización explícita y `Notificacion` no
    # lleva `AutoriaMixin`, así que nada de lo que se escribe sale del
    # contexto. Mover el ContextVar sería peor — el resto de `enviar_a`
    # (numeración, autoría) seguiría después creyendo que es del proveedor.
    await fijar_organizacion_activa(session, org_proveedor)
    try:
        await notificaciones_service.crear(
            session,
            organization_id=org_proveedor,
            tipo=notificaciones_service.TIPO_SOLICITUD_PRECIOS,
            titulo=f"{emisor or 'Una empresa'} te pide precio: {solicitud.titulo}",
            cuerpo=(
                "Puedes aceptarla y se convertirá en un presupuesto tuyo, con sus partidas "
                "y mediciones, para que lo valores con tus precios."
            ),
            enlace=f"/oferta/{token}",
            importante=True,
            token_acceso=token,
        )
    finally:
        await fijar_organizacion_activa(session, org_emisor)
    return True


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


async def listar_por_obra(
    session: AsyncSession, obra_id: uuid.UUID
) -> list[SolicitudPrecios]:
    """Los paquetes de precios de TODOS los presupuestos que ejecuta la obra.

    Las solicitudes se piden mientras se presupuesta, pero es en obra donde
    hacen falta: saber a qué proveedor se adjudicó cada partida es lo que
    convierte el comparativo en el punto de partida de las compras.

    Vive aquí y no en `obras` por la dirección de dependencias: `compras`
    importa `obras`, no al revés (`ModuleRegistry._detect_cycles()` lo
    prohíbe). Mismo truco que `compras/costes.py`, que sirve
    `/api/obras/{id}/costes`.
    """
    from app.modules.obras.models import ObraPresupuesto

    org_id = require_organization_id()
    filas = (
        await session.execute(
            select(SolicitudPrecios)
            .join(
                ObraPresupuesto,
                ObraPresupuesto.presupuesto_id == SolicitudPrecios.presupuesto_id,
            )
            .where(
                ObraPresupuesto.obra_id == obra_id,
                SolicitudPrecios.organization_id == org_id,
            )
            .order_by(ObraPresupuesto.orden, SolicitudPrecios.codigo)
        )
    ).scalars()
    return list(filas)


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
