"""Tickets, wiki y el índice de búsqueda."""

import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import require_organization_id
from app.modules.soporte import embeddings
from app.modules.soporte.enums import EstadoTicket, OrigenFragmento
from app.modules.soporte.models import Fragmento, PaginaWiki, Ticket

logger = logging.getLogger(__name__)

#: Cuántos trozos se le pasan al asistente como contexto. Más no mejora la
#: respuesta y sí infla el prompt: con cinco trozos de 900 caracteres ya hay
#: material de sobra para responder o para decir que no se sabe.
TROZOS_CONTEXTO = 5

#: Distancia coseno por encima de la cual un fragmento se descarta. Medido
#: contra la wiki real: una pregunta que la página responde queda en 0,19-0,28;
#: una pregunta del dominio que la página NO responde, en 0,39; algo ajeno por
#: completo, en 0,48-0,51. Sin este corte la búsqueda siempre devuelve algo —
#: lo más parecido que haya— y el asistente acabaría respondiendo con la
#: página que menos desencaja en vez de admitir que no lo sabe.
DISTANCIA_MAXIMA = 0.35


def slugificar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^a-z0-9]+", "-", sin_tildes).strip("-")
    return limpio[:160] or "pagina"


async def siguiente_codigo(session: AsyncSession) -> str:
    return await siguiente_referencia_libre(
        session,
        organization_id=require_organization_id(),
        tipo_documento="ticket",
        existe=lambda c: _existe_codigo(session, c),
    )


async def _existe_codigo(session: AsyncSession, codigo: str) -> bool:
    return bool(
        await session.scalar(
            select(Ticket.id).where(
                Ticket.organization_id == require_organization_id(), Ticket.codigo == codigo
            )
        )
    )


# ── Índice de búsqueda ──────────────────────────────────────────────────


async def indexar_pagina(session: AsyncSession, pagina: PaginaWiki) -> int:
    """Rehace los fragmentos de una página. Devuelve cuántos quedaron.

    NUNCA lanza: si Gemini no contesta, la página se ha guardado igual y lo
    único que pasa es que todavía no se puede buscar por significado. Una
    wiki sin indexar sigue siendo una wiki; una wiki que no deja guardar, no.
    """
    try:
        return await _indexar_pagina(session, pagina)
    except embeddings.SinEmbeddings as exc:
        logger.warning("No se ha podido indexar «%s»: %s", pagina.titulo, exc)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo indexando «%s»: %s", pagina.titulo, exc)
        return 0


async def _indexar_pagina(session: AsyncSession, pagina: PaginaWiki) -> int:
    await session.execute(
        delete(Fragmento).where(
            Fragmento.origen == OrigenFragmento.WIKI, Fragmento.origen_id == pagina.id
        )
    )
    if not pagina.publicada:
        # Una página en borrador no debe salir en las respuestas del
        # asistente: se borra del índice y no se vuelve a meter.
        await session.flush()
        return 0

    # El título va al principio de cada trozo. Sin él, un trozo del medio de
    # la página pierde de qué trata y el vector lo coloca lejos de la
    # pregunta que debería responder.
    trozos = embeddings.trocear(pagina.contenido)
    if not trozos:
        await session.flush()
        return 0
    con_titulo = [f"{pagina.titulo}. {t}" for t in trozos]

    vectores = await embeddings.vectorizar(session, con_titulo)
    for i, (texto, vector) in enumerate(zip(trozos, vectores, strict=True)):
        session.add(
            Fragmento(
                organization_id=pagina.organization_id,
                origen=OrigenFragmento.WIKI,
                origen_id=pagina.id,
                titulo=pagina.titulo,
                texto=texto,
                orden=i,
                embedding=vector,
            )
        )
    pagina.indexada_en = datetime.now(UTC)
    await session.flush()
    return len(trozos)


async def buscar(
    session: AsyncSession,
    pregunta: str,
    *,
    limite: int = TROZOS_CONTEXTO,
    distancia_maxima: float = DISTANCIA_MAXIMA,
) -> list[dict]:
    """Los fragmentos más parecidos a la pregunta.

    Devuelve la distancia junto al texto: quien llama decide si un resultado
    lejano vale o no. Sin ese número, el asistente no puede distinguir «esto
    lo responde la wiki» de «lo más parecido que hay, que no tiene nada que
    ver».
    """
    try:
        vector = (await embeddings.vectorizar(session, [pregunta], para_consulta=True))[0]
    except embeddings.SinEmbeddings as exc:
        logger.info("Búsqueda sin embeddings: %s", exc)
        return []

    distancia = Fragmento.embedding.cosine_distance(vector)
    filas = (
        await session.execute(
            select(Fragmento, distancia.label("distancia"))
            .where(
                Fragmento.organization_id == require_organization_id(),
                distancia <= distancia_maxima,
            )
            .order_by(distancia)
            .limit(limite)
        )
    ).all()
    return [
        {
            "titulo": f.titulo,
            "texto": f.texto,
            "origen": f.origen.value,
            "origen_id": str(f.origen_id),
            # 0 = idéntico, 2 = opuesto. Por encima de ~0,6 ya es ruido.
            "distancia": round(float(d), 4),
        }
        for f, d in filas
    ]


async def reindexar_todo(session: AsyncSession) -> dict:
    """Reconstruye el índice de toda la wiki. Para después de cambiar de
    modelo de embeddings, o si algo quedó a medias."""
    paginas = list(
        await session.scalars(
            select(PaginaWiki).where(
                PaginaWiki.organization_id == require_organization_id()
            )
        )
    )
    total = 0
    fallos = 0
    for pagina in paginas:
        trozos = await indexar_pagina(session, pagina)
        total += trozos
        if trozos == 0 and pagina.publicada and pagina.contenido.strip():
            fallos += 1
    return {"paginas": len(paginas), "fragmentos": total, "sin_indexar": fallos}


async def marcar_resuelto(ticket: Ticket) -> None:
    ticket.estado = EstadoTicket.RESUELTO
    ticket.resuelto_en = datetime.now(UTC)


async def obtener_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    return await session.scalar(
        select(Ticket).where(
            Ticket.id == ticket_id, Ticket.organization_id == require_organization_id()
        )
    )


async def obtener_pagina(session: AsyncSession, pagina_id: uuid.UUID) -> PaginaWiki | None:
    return await session.scalar(
        select(PaginaWiki).where(
            PaginaWiki.id == pagina_id,
            PaginaWiki.organization_id == require_organization_id(),
        )
    )
