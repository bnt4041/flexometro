import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.soporte import service
from app.modules.soporte.enums import EstadoTicket, OrigenFragmento
from app.modules.soporte.models import Fragmento, MensajeTicket, PaginaWiki, Ticket
from app.modules.soporte.schemas import (
    MensajeIn,
    PaginaIn,
    PaginaOut,
    ResultadoBusqueda,
    TicketIn,
    TicketOut,
    TicketUpdate,
)

router = APIRouter(
    prefix="/api/soporte", tags=["soporte"], dependencies=[Depends(require_module("soporte"))]
)


def _pagina_out(pagina: PaginaWiki) -> PaginaOut:
    salida = PaginaOut.model_validate(pagina)
    salida.indice_al_dia = bool(
        pagina.indexada_en and pagina.indexada_en >= pagina.updated_at
    )
    return salida


# ── Tickets ─────────────────────────────────────────────────────────────
#
# Abrir un ticket y responder al propio NO piden permiso de módulo: quien
# menos permisos tiene es justo quien más necesita poder pedir ayuda. Lo que
# sí lo pide es gestionarlos (asignar, cerrar) y ver los de los demás.


@router.get("/tickets", response_model=list[TicketOut])
async def listar_tickets(
    mios: bool = False,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[TicketOut]:
    """Sin permiso de módulo se ven solo los propios; con él, todos."""
    from app.core.permisos import permiso_efectivo

    permiso = await permiso_efectivo(session, principal, "soporte")
    consulta = select(Ticket).where(Ticket.organization_id == require_organization_id())
    if mios or permiso.ver == Alcance.NINGUNO or permiso.ver == Alcance.PROPIOS:
        consulta = consulta.where(Ticket.creado_por_subject == principal.subject)
    filas = await session.scalars(consulta.order_by(Ticket.created_at.desc()).limit(200))
    return [TicketOut.model_validate(f) for f in filas]


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def crear_ticket(
    datos: TicketIn,
    session: AsyncSession = Depends(get_session),
) -> TicketOut:
    ticket = Ticket(
        organization_id=require_organization_id(),
        codigo=await service.siguiente_codigo(session),
        titulo=datos.titulo,
        descripcion=datos.descripcion,
        tipo=datos.tipo,
        prioridad=datos.prioridad,
        ruta_origen=datos.ruta_origen,
        **datos_autoria(),
    )
    session.add(ticket)
    await session.flush()
    await session.refresh(ticket, ["mensajes"])
    return TicketOut.model_validate(ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def ver_ticket(
    ticket_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> TicketOut:
    ticket = await _ticket_visible(session, ticket_id, principal)
    salida = TicketOut.model_validate(ticket)
    # Las notas internas no se le enseñan a quien abrió el ticket.
    if ticket.creado_por_subject == principal.subject:
        permiso = await _puede_gestionar(session, principal)
        if not permiso:
            salida.mensajes = [m for m in salida.mensajes if not m.interno]
    return salida


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def actualizar_ticket(
    ticket_id: uuid.UUID,
    datos: TicketUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("soporte", "editar")),
) -> TicketOut:
    ticket = await service.obtener_ticket(session, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("estado") == EstadoTicket.RESUELTO:
        await service.marcar_resuelto(ticket)
        cambios.pop("estado")
    for campo, valor in cambios.items():
        setattr(ticket, campo, valor)
    await session.flush()
    await session.refresh(ticket, ["mensajes"])
    return TicketOut.model_validate(ticket)


@router.post("/tickets/{ticket_id}/mensajes", response_model=TicketOut)
async def responder(
    ticket_id: uuid.UUID,
    datos: MensajeIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> TicketOut:
    ticket = await _ticket_visible(session, ticket_id, principal)
    interno = datos.interno and await _puede_gestionar(session, principal)
    session.add(
        MensajeTicket(
            organization_id=ticket.organization_id,
            ticket_id=ticket.id,
            cuerpo=datos.cuerpo,
            interno=interno,
            **datos_autoria(),
        )
    )
    # Responder reabre: un ticket resuelto al que alguien contesta es que no
    # estaba resuelto.
    if ticket.estado in (EstadoTicket.RESUELTO, EstadoTicket.CERRADO):
        ticket.estado = EstadoTicket.ABIERTO
    await session.flush()
    await session.refresh(ticket, ["mensajes"])
    return TicketOut.model_validate(ticket)


async def _puede_gestionar(session: AsyncSession, principal: Principal) -> bool:
    from app.core.permisos import permiso_efectivo

    permiso = await permiso_efectivo(session, principal, "soporte")
    return permiso.editar != Alcance.NINGUNO


async def _ticket_visible(
    session: AsyncSession, ticket_id: uuid.UUID, principal: Principal
) -> Ticket:
    ticket = await service.obtener_ticket(session, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    if ticket.creado_por_subject == principal.subject:
        return ticket
    if await _puede_gestionar(session, principal):
        return ticket
    # Mismo 404 que si no existiera: decir «existe pero no es tuyo» ya
    # confirma que existe.
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")


# ── Wiki ────────────────────────────────────────────────────────────────


@router.get("/wiki", response_model=list[PaginaOut])
async def listar_paginas(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[PaginaOut]:
    """Todas las publicadas. Los borradores, solo para quien puede editar."""
    consulta = select(PaginaWiki).where(
        PaginaWiki.organization_id == require_organization_id()
    )
    if not await _puede_gestionar(session, principal):
        consulta = consulta.where(PaginaWiki.publicada.is_(True))
    filas = await session.scalars(consulta.order_by(PaginaWiki.categoria, PaginaWiki.titulo))
    return [_pagina_out(f) for f in filas]


@router.post("/wiki", response_model=PaginaOut, status_code=status.HTTP_201_CREATED)
async def crear_pagina(
    datos: PaginaIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("soporte", "crear")),
) -> PaginaOut:
    pagina = PaginaWiki(
        organization_id=require_organization_id(),
        slug=service.slugificar(datos.titulo),
        titulo=datos.titulo,
        contenido=datos.contenido,
        categoria=datos.categoria,
        publicada=datos.publicada,
        **datos_autoria(),
    )
    session.add(pagina)
    await session.flush()
    await service.indexar_pagina(session, pagina)
    return _pagina_out(pagina)


@router.put("/wiki/{pagina_id}", response_model=PaginaOut)
async def actualizar_pagina(
    pagina_id: uuid.UUID,
    datos: PaginaIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("soporte", "editar")),
) -> PaginaOut:
    pagina = await service.obtener_pagina(session, pagina_id)
    if pagina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrada")
    cambio_texto = pagina.contenido != datos.contenido or pagina.titulo != datos.titulo
    pagina.titulo = datos.titulo
    pagina.contenido = datos.contenido
    pagina.categoria = datos.categoria
    pagina.publicada = datos.publicada
    pagina.version += 1
    await session.flush()
    # Solo se reindexa si cambió el texto: cada indexación cuesta una llamada
    # a Gemini, y corregir la categoría no cambia lo que dice la página.
    if cambio_texto or not pagina.publicada:
        await service.indexar_pagina(session, pagina)
    return _pagina_out(pagina)


@router.delete("/wiki/{pagina_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_pagina(
    pagina_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("soporte", "borrar")),
) -> None:
    pagina = await service.obtener_pagina(session, pagina_id)
    if pagina is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrada")
    from sqlalchemy import delete as sql_delete

    await session.execute(
        sql_delete(Fragmento).where(
            Fragmento.origen == OrigenFragmento.WIKI, Fragmento.origen_id == pagina.id
        )
    )
    await session.delete(pagina)
    await session.flush()


@router.post("/wiki/reindexar")
async def reindexar(
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("soporte", "editar")),
) -> dict:
    return await service.reindexar_todo(session)


@router.get("/buscar", response_model=list[ResultadoBusqueda])
async def buscar(
    q: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[ResultadoBusqueda]:
    """Búsqueda por significado sobre la wiki. La usa el asistente y también
    el buscador de la pantalla de ayuda."""
    return [ResultadoBusqueda(**r) for r in await service.buscar(session, q)]
