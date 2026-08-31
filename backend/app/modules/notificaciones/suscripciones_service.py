"""Alta y mantenimiento de las suscripciones, desde la ficha de cada uno."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos as catalogo
from app.core.tenancy import require_organization_id
from app.modules.notificaciones import service
from app.modules.notificaciones.models import PreferenciaUsuario, SuscripcionAviso


class SuscripcionInvalida(Exception):
    pass


def _normalizar_parametros(codigo: str, crudos: dict) -> dict:
    """Los huecos del evento, dentro de su rango y con los que falten
    rellenos. Un «avisar a los 0 días» dispararía en cada pasada sobre todo
    lo que existe."""
    evento = catalogo.obtener(codigo)
    if evento is None:
        raise SuscripcionInvalida(f"No existe el evento «{codigo}»")

    limpios = {}
    for parametro in evento.parametros:
        valor = crudos.get(parametro.nombre, parametro.por_defecto)
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise SuscripcionInvalida(f"«{parametro.etiqueta}» tiene que ser un número entero")
        if not parametro.minimo <= valor <= parametro.maximo:
            raise SuscripcionInvalida(
                f"«{parametro.etiqueta}» tiene que estar entre "
                f"{parametro.minimo} y {parametro.maximo}"
            )
        limpios[parametro.nombre] = valor
    return limpios


async def listar(
    session: AsyncSession,
    *,
    usuario_subject: str | None = None,
    grupo_id: uuid.UUID | None = None,
) -> list[SuscripcionAviso]:
    """Las de una persona o las de un grupo. Sin filtro, todas."""
    org_id = require_organization_id()
    consulta = select(SuscripcionAviso).where(SuscripcionAviso.organization_id == org_id)
    if usuario_subject:
        consulta = consulta.where(SuscripcionAviso.usuario_subject == usuario_subject)
    if grupo_id:
        consulta = consulta.where(SuscripcionAviso.grupo_id == grupo_id)
    return list(await session.scalars(consulta.order_by(SuscripcionAviso.tipo_evento)))


async def guardar(
    session: AsyncSession,
    *,
    tipo_evento: str,
    usuario_subject: str | None,
    grupo_id: uuid.UUID | None,
    canales: list[str],
    parametros: dict,
    activa: bool = True,
) -> SuscripcionAviso | None:
    """Crea o actualiza la suscripción de ese destinatario a ese evento.

    Sin canales se BORRA en vez de guardarse vacía: una suscripción que no
    avisa por ningún sitio es lo mismo que no estar suscrito, y dejarla ahí
    solo sirve para creer que sí. Devuelve `None` en ese caso.
    """
    if bool(usuario_subject) == bool(grupo_id):
        raise SuscripcionInvalida("Es de una persona o de un grupo, no de las dos cosas")

    desconocidos = set(canales) - set(service.CANALES_POSIBLES)
    if desconocidos:
        raise SuscripcionInvalida(f"Canales desconocidos: {', '.join(sorted(desconocidos))}")

    limpios = _normalizar_parametros(tipo_evento, parametros)
    org_id = require_organization_id()

    existente = await session.scalar(
        select(SuscripcionAviso).where(
            SuscripcionAviso.organization_id == org_id,
            SuscripcionAviso.tipo_evento == tipo_evento,
            SuscripcionAviso.usuario_subject == usuario_subject,
            SuscripcionAviso.grupo_id == grupo_id,
        )
    )

    if not canales:
        if existente is not None:
            await session.delete(existente)
            await session.flush()
        return None

    if existente is None:
        existente = SuscripcionAviso(
            organization_id=org_id,
            tipo_evento=tipo_evento,
            usuario_subject=usuario_subject,
            grupo_id=grupo_id,
        )
        session.add(existente)

    existente.canales = sorted(set(canales))
    existente.parametros = limpios
    existente.activa = activa
    await session.flush()
    return existente


async def preferencia_de(session: AsyncSession, subject: str) -> PreferenciaUsuario:
    org_id = require_organization_id()
    fila = await session.scalar(
        select(PreferenciaUsuario).where(
            PreferenciaUsuario.organization_id == org_id,
            PreferenciaUsuario.usuario_subject == subject,
        )
    )
    if fila is None:
        fila = PreferenciaUsuario(organization_id=org_id, usuario_subject=subject)
        session.add(fila)
        await session.flush()
    return fila
