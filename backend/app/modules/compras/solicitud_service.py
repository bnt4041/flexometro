"""Alta, edición y envío de una solicitud de precios a un proveedor.

Lo que se guarda en `SolicitudLinea` es una COPIA CONGELADA de la partida, no
una referencia viva: si el presupuesto se edita después de mandar la separata,
lo que el proveedor está cotizando no puede cambiarle bajo los pies.
`partida_id` queda solo como rastro, para poder volcar después la oferta sobre
la partida correcta.

Crear y enviar son dos pasos separados: `crear_solicitud` deja la solicitud en
`BORRADOR`, editable (`actualizar_lineas`/`actualizar_datos`) desde la pestaña
Comparativo hasta que `enviar_solicitud` la cierra — es en ESE momento cuando
se genera el token de acceso del proveedor, no antes: mientras es un borrador
no hay ningún enlace vivo que pueda filtrarse.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mailer import MailerError, enviar_correo
from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import datos_autoria, require_organization_id, require_principal
from app.modules.compras.models import (
    AccesoEstado,
    AccesoToken,
    EstadoSolicitud,
    SolicitudLinea,
    SolicitudPrecios,
)
from app.modules.compras.publico_acceso import generar_token
from app.modules.core import correo
from app.modules.core.settings_service import configuracion_smtp_de
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


class SolicitudNoEditable(Exception):
    """La solicitud ya salió (o se descartó): sus líneas quedaron congeladas
    en lo que vio el proveedor y no se pueden tocar desde aquí."""

    pass


class SolicitudYaEnviada(Exception):
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
    {EstadoSolicitud.BORRADOR, EstadoSolicitud.ENVIADA, EstadoSolicitud.RESPONDIDA}
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


async def _lineas_desde_partidas(
    session: AsyncSession, *, presupuesto_id: uuid.UUID, partida_ids: list[uuid.UUID]
) -> list[tuple[Partida, str]]:
    """Partida + resumen de su capítulo, acotado SIEMPRE a presupuesto y
    organización: los ids llegan del cliente y no se pueden dar por buenos."""
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


async def crear_solicitud(
    session: AsyncSession,
    *,
    presupuesto_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    partida_ids: list[uuid.UUID],
    fecha_limite: date | None = None,
    notas: str | None = None,
) -> SolicitudPrecios:
    """Deja la solicitud en `BORRADOR`. No genera ningún acceso ni manda
    nada — eso es cosa de `enviar_solicitud`, un paso aparte y explícito."""
    org_id = require_organization_id()

    presupuesto = await session.scalar(
        select(Presupuesto).where(
            Presupuesto.id == presupuesto_id, Presupuesto.organization_id == org_id
        )
    )
    if presupuesto is None:
        raise PresupuestoInvalido("El presupuesto no existe en esta organización")

    proveedor = await session.scalar(
        select(Tercero).where(Tercero.id == proveedor_id, Tercero.organization_id == org_id)
    )
    if proveedor is None:
        raise ProveedorInvalido("El proveedor no existe en esta organización")
    if not proveedor.es_proveedor:
        raise ProveedorInvalido(f"«{proveedor.razon_social}» no está marcado como proveedor")

    filas = await _lineas_desde_partidas(
        session, presupuesto_id=presupuesto_id, partida_ids=partida_ids
    )
    if not filas:
        raise SinPartidas("No hay ninguna partida válida en la selección")

    principal = require_principal()
    solicitud = SolicitudPrecios(
        organization_id=org_id,
        codigo=await _codigo_libre(session),
        presupuesto_id=presupuesto_id,
        proveedor_id=proveedor_id,
        estado=EstadoSolicitud.BORRADOR,
        fecha_limite=fecha_limite,
        notas=notas,
        emisor_subject=principal.subject,
        emisor_nombre=principal.username,
        **datos_autoria(),
    )
    session.add(solicitud)
    await session.flush()

    for orden, (partida, capitulo_resumen) in enumerate(filas):
        session.add(
            SolicitudLinea(
                organization_id=org_id,
                solicitud_id=solicitud.id,
                partida_id=partida.id,
                capitulo_resumen=capitulo_resumen,
                codigo=partida.codigo,
                resumen=partida.resumen,
                texto=partida.texto,
                unidad=partida.unidad,
                medicion=partida.medicion,
                orden=orden,
            )
        )
    await session.flush()
    return solicitud


async def actualizar_lineas(
    session: AsyncSession, solicitud: SolicitudPrecios, partida_ids: list[uuid.UUID]
) -> None:
    """Añade/quita partidas de un borrador. Diferencial por `partida_id`: las
    que se mantienen no se tocan (si el proveedor ya hubiera escrito algo ahí
    no se perdería), solo se borran las que salen y se insertan las nuevas."""
    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise SolicitudNoEditable("Esta solicitud ya no se puede editar")

    filas = await _lineas_desde_partidas(
        session, presupuesto_id=solicitud.presupuesto_id, partida_ids=partida_ids
    )
    if not filas:
        raise SinPartidas("No hay ninguna partida válida en la selección")

    actuales = (
        await session.execute(
            select(SolicitudLinea).where(SolicitudLinea.solicitud_id == solicitud.id)
        )
    ).scalars().all()
    por_partida = {l.partida_id: l for l in actuales}
    nuevos_ids = {partida.id for partida, _ in filas}

    for linea in actuales:
        if linea.partida_id not in nuevos_ids:
            await session.delete(linea)

    org_id = require_organization_id()
    orden_base = len(nuevos_ids)
    for orden, (partida, capitulo_resumen) in enumerate(filas):
        if partida.id in por_partida:
            continue
        session.add(
            SolicitudLinea(
                organization_id=org_id,
                solicitud_id=solicitud.id,
                partida_id=partida.id,
                capitulo_resumen=capitulo_resumen,
                codigo=partida.codigo,
                resumen=partida.resumen,
                texto=partida.texto,
                unidad=partida.unidad,
                medicion=partida.medicion,
                orden=orden_base + orden,
            )
        )
    await session.flush()


async def actualizar_datos(
    session: AsyncSession, solicitud: SolicitudPrecios, cambios: dict
) -> None:
    """`cambios` es un `SolicitudActualizar.model_dump(exclude_unset=True)`:
    solo toca lo que el cliente mandó explícitamente."""
    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise SolicitudNoEditable("Esta solicitud ya no se puede editar")
    for campo, valor in cambios.items():
        setattr(solicitud, campo, valor)
    await session.flush()


async def eliminar_borrador(session: AsyncSession, solicitud: SolicitudPrecios) -> None:
    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise SolicitudNoEditable("Esta solicitud ya no se puede eliminar")
    await session.delete(solicitud)
    await session.flush()


async def _emitir_acceso(session: AsyncSession, solicitud: SolicitudPrecios) -> str:
    """Crea el acceso del proveedor y devuelve la URL EN CLARO, que es la
    única vez que existe: en base de datos solo queda el hash.

    Emitir invalida cualquier acceso anterior de esta solicitud — no se puede
    "recuperar" el enlace ya mandado (por diseño, ver `publico_acceso.py`),
    así que pedir uno nuevo necesariamente jubila al viejo.
    """
    org_id = require_organization_id()

    anteriores = (
        await session.execute(
            select(AccesoToken).where(AccesoToken.solicitud_id == solicitud.id)
        )
    ).scalars().all()
    for anterior in anteriores:
        await session.delete(anterior)
    await session.flush()

    token, token_hash = generar_token()
    session.add(
        AccesoToken(organization_id=org_id, token_hash=token_hash, solicitud_id=solicitud.id)
    )

    caduca = datetime.now(UTC) + timedelta(days=DIAS_VALIDEZ_POR_DEFECTO)
    if solicitud.fecha_limite is not None:
        # Margen sobre la fecha límite: que el enlace no muera justo el día
        # que el proveedor iba a contestar.
        limite = datetime.combine(
            solicitud.fecha_limite, datetime.min.time(), tzinfo=UTC
        ) + timedelta(days=7)
        caduca = max(caduca, limite)

    estado = await session.scalar(
        select(AccesoEstado).where(AccesoEstado.solicitud_id == solicitud.id)
    )
    if estado is None:
        session.add(
            AccesoEstado(organization_id=org_id, solicitud_id=solicitud.id, expira_en=caduca)
        )
    else:
        # El estado (usos, revocado…) es de la SOLICITUD, no del token: se
        # reutiliza la fila y solo se reabre la ventana de validez.
        estado.expira_en = caduca
        estado.revocado = False
    await session.flush()

    return f"{get_settings().frontend_url.rstrip('/')}/oferta/{token}"


async def enviar_solicitud(session: AsyncSession, solicitud: SolicitudPrecios) -> str:
    """Genera el acceso del proveedor, manda el correo y marca la solicitud
    como enviada. Devuelve la URL, para poder ofrecer "copiar enlace" justo
    después sin tener que emitir otro (que invalidaría el recién mandado).

    Deja que `MailerError` se propague — igual que en el resto de la
    aplicación, el envío es best-effort y quien llama decide si sigue
    adelante o avisa."""
    if solicitud.estado != EstadoSolicitud.BORRADOR:
        raise SolicitudYaEnviada("Esta solicitud ya se envió")

    org_id = require_organization_id()

    presupuesto = await session.scalar(
        select(Presupuesto).where(Presupuesto.id == solicitud.presupuesto_id)
    )
    proveedor = await session.scalar(select(Tercero).where(Tercero.id == solicitud.proveedor_id))
    if proveedor is None or not proveedor.email:
        raise SinCorreoDeProveedor(
            "Este proveedor no tiene correo. Usa «Copiar enlace» y pásaselo tú, "
            "o añade su email en su ficha."
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

    url = await _emitir_acceso(session, solicitud)

    cuerpo = correo.render_solicitud_precios(
        emisor_nombre=emisor_nombre or "",
        proveedor_nombre=proveedor.razon_social,
        presupuesto_nombre=presupuesto.nombre if presupuesto else "",
        num_lineas=total_lineas,
        notas=solicitud.notas,
        fecha_limite=solicitud.fecha_limite.isoformat() if solicitud.fecha_limite else None,
        url_oferta=url,
    )

    config = await configuracion_smtp_de(session, org_id)
    await enviar_correo(
        config,
        destinatario=proveedor.email,
        asunto=f"Solicitud de precios — {presupuesto.nombre if presupuesto else solicitud.codigo}",
        cuerpo_html=cuerpo,
    )

    solicitud.estado = EstadoSolicitud.ENVIADA
    solicitud.enviada_en = datetime.now(UTC)
    await session.flush()
    return url


async def generar_enlace(session: AsyncSession, solicitud: SolicitudPrecios) -> str:
    """Enlace para pasárselo al proveedor por el medio que sea (WhatsApp, un
    correo escrito a mano…) en vez de mandarlo desde aquí.

    Emite uno NUEVO cada vez, y el anterior deja de funcionar: el token solo
    se guarda hasheado, así que no hay forma de volver a enseñar el que ya se
    mandó. Un borrador queda marcado como enviado — a partir de que el enlace
    existe, sus líneas ya no se pueden tocar."""
    if solicitud.estado not in _ESTADOS_CON_ENLACE:
        raise SolicitudNoEditable("Esta solicitud ya está cerrada")

    url = await _emitir_acceso(session, solicitud)
    if solicitud.estado == EstadoSolicitud.BORRADOR:
        solicitud.estado = EstadoSolicitud.ENVIADA
        solicitud.enviada_en = datetime.now(UTC)
    await session.flush()
    return url


async def listar_por_presupuesto(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[tuple[SolicitudPrecios, Tercero]]:
    """Todas las solicitudes hechas sobre este presupuesto (borradores
    incluidos), con el proveedor ya resuelto — es lo que alimenta el
    comparativo."""
    org_id = require_organization_id()
    filas = (
        await session.execute(
            select(SolicitudPrecios, Tercero)
            .join(Tercero, Tercero.id == SolicitudPrecios.proveedor_id)
            .where(
                SolicitudPrecios.presupuesto_id == presupuesto_id,
                SolicitudPrecios.organization_id == org_id,
            )
            .order_by(SolicitudPrecios.codigo)
        )
    ).all()
    return [(s, proveedor) for s, proveedor in filas]


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
