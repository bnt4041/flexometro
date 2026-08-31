"""Aplicar una propuesta que la persona ha confirmado.

Aquí se vuelve a comprobar el permiso desde cero. Parece redundante —la
herramienta ya lo miró al proponer— pero no lo es: entre la propuesta y la
confirmación la propuesta ha estado en el navegador, y lo que vuelve es un
JSON como cualquier otro. Lo único que se cree de él es qué se pidió; si se
puede hacer se decide otra vez aquí, contra el permiso de ahora.

Nada escribe en las tablas directamente: todo pasa por el servicio del módulo
dueño, igual que el importador. Así el copiloto hereda la numeración, la
validación y la auditoría, y no puede colar por detrás una fila que la
pantalla nunca aceptaría por delante.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.enums import Alcance


class PropuestaInvalida(Exception):
    """No se puede aplicar: o no existe la acción, o falta permiso, o los
    datos ya no valen."""


@dataclass(frozen=True)
class Aplicada:
    descripcion: str
    ruta: str | None = None


async def aplicar(
    session: AsyncSession,
    principal: Principal,
    accion: str,
    datos: dict[str, Any],
) -> Aplicada:
    if accion.startswith("crear:"):
        return await _aplicar_crear(session, principal, accion.removeprefix("crear:"), datos)
    if accion == "abrir_ticket":
        return await _aplicar_ticket(session, principal, datos)
    raise PropuestaInvalida(f"No sé aplicar «{accion}»")


async def _exigir(session: AsyncSession, principal: Principal, modulo: str, accion: str) -> None:
    from app.core.permisos import permiso_efectivo
    from app.modules.core.service import active_module_codes

    if modulo not in set(await active_module_codes(session, principal.organization_id)):
        raise PropuestaInvalida(f"El módulo «{modulo}» no está activo")
    permiso = await permiso_efectivo(session, principal, modulo)
    if permiso.de(accion) == Alcance.NINGUNO:
        raise PropuestaInvalida(f"Sin permiso de «{accion}» en «{modulo}»")


async def _aplicar_crear(
    session: AsyncSession, principal: Principal, codigo: str, datos: dict
) -> Aplicada:
    from app.modules.importador import destinos

    destino = destinos.obtener(codigo)
    if destino is None:
        raise PropuestaInvalida(f"«{codigo}» no es un destino conocido")
    await _exigir(session, principal, destino.modulo, "crear")

    # Se vuelve a filtrar por los campos declarados: lo que vuelve del
    # navegador podría traer claves de más, y pasárselas al servicio sería
    # dejar que el cliente decida qué columnas se tocan.
    permitidos = {c.nombre for c in destino.campos}
    limpios = {k: v for k, v in datos.items() if k in permitidos and v not in (None, "")}

    creador = destinos.creador_de(codigo)
    if creador is None:
        raise PropuestaInvalida(f"«{codigo}» no sabe crear nada")
    try:
        descripcion = await creador(session, limpios)
    except destinos.FilaInvalida as exc:
        raise PropuestaInvalida(str(exc)) from exc
    await session.flush()
    return Aplicada(descripcion=descripcion)


async def _aplicar_ticket(session: AsyncSession, principal: Principal, datos: dict) -> Aplicada:
    from app.core.tenancy import datos_autoria, require_organization_id
    from app.modules.core.service import active_module_codes
    from app.modules.soporte import service as soporte
    from app.modules.soporte.enums import Prioridad, TipoTicket
    from app.modules.soporte.models import Ticket

    if "soporte" not in set(await active_module_codes(session, principal.organization_id)):
        raise PropuestaInvalida("El módulo «soporte» no está activo")

    titulo = (datos.get("titulo") or "").strip()
    descripcion = (datos.get("descripcion") or "").strip()
    if not titulo or not descripcion:
        raise PropuestaInvalida("Un ticket necesita asunto y descripción")

    try:
        tipo = TipoTicket(datos.get("tipo") or "incidencia")
        prioridad = Prioridad(datos.get("prioridad") or "normal")
    except ValueError as exc:
        raise PropuestaInvalida(str(exc)) from exc

    ticket = Ticket(
        organization_id=require_organization_id(),
        codigo=await soporte.siguiente_codigo(session),
        titulo=titulo,
        descripcion=descripcion,
        tipo=tipo,
        prioridad=prioridad,
        ruta_origen=datos.get("ruta_origen"),
        **datos_autoria(),
    )
    session.add(ticket)
    await session.flush()
    return Aplicada(descripcion=f"Ticket {ticket.codigo} abierto", ruta="/soporte")
