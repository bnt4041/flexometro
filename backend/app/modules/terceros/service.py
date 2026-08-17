"""Servicios de terceros.

El `organization_id` no se recibe por parámetro: se lee del contexto de la
request (`require_organization_id`). Así un fallo en un router no puede filtrar
datos de otra organización, porque no hay forma de pedirlos.

Tercero/Contacto son maestros compartibles (Fase 15): los listados y el
detalle de solo lectura de Tercero (`obtener_tercero_visible`) usan
`organizaciones_visibles()`, que además de la propia organización incluye
las hermanas de la misma cuenta cuando esta tiene `compartir_maestros`
activo — Contacto solo se lee embebido en `Tercero.contactos`
(`selectinload`), nunca por sí solo, así que le basta con que su tabla
tenga el RLS ampliado (`convertir_a_rls_maestro`), sin una función
`_visible` propia. Las altas, ediciones y bajas SIGUEN atadas siempre a la
organización propia (`obtener_tercero`/`obtener_contacto`, sin "_visible")
— el RLS de la tabla (`WITH CHECK`) lo exige igual, esto es además una
segunda barrera a nivel de aplicación.
"""

import re
import uuid

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenancy import datos_autoria, require_organization_id
from app.core.visibilidad import organizaciones_visibles
from app.modules.terceros.models import Contacto, ContactoAsociado, EntidadContacto, Tercero
from app.modules.terceros.schemas import (
    ContactoAsociadoCreate,
    ContactoBase,
    ContactoCreate,
    ContactoUpdate,
    TerceroCreate,
    TerceroUpdate,
)

PREFIJO_CODIGO = "T"
_RE_CODIGO = re.compile(rf"^{PREFIJO_CODIGO}(\d+)$")


class CodigoDuplicado(Exception):
    pass


class AsociacionDuplicada(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    """Siguiente correlativo de la organización, en formato T00001."""
    org_id = require_organization_id()
    codigos = await session.execute(
        select(Tercero.codigo).where(Tercero.organization_id == org_id)
    )
    maximo = 0
    for (codigo,) in codigos.all():
        match = _RE_CODIGO.match(codigo)
        if match:
            maximo = max(maximo, int(match.group(1)))
    return f"{PREFIJO_CODIGO}{maximo + 1:05d}"


def _filtrar(stmt: Select, q: str | None, rol: str | None, activo: bool | None) -> Select:
    if q:
        patron = f"%{q}%"
        stmt = stmt.where(
            or_(
                Tercero.razon_social.ilike(patron),
                Tercero.nombre_comercial.ilike(patron),
                Tercero.nif.ilike(patron),
                Tercero.codigo.ilike(patron),
            )
        )
    if rol == "cliente":
        stmt = stmt.where(Tercero.es_cliente.is_(True))
    elif rol == "proveedor":
        stmt = stmt.where(Tercero.es_proveedor.is_(True))
    elif rol == "subcontratista":
        stmt = stmt.where(Tercero.es_subcontratista.is_(True))
    if activo is not None:
        stmt = stmt.where(Tercero.activo.is_(activo))
    return stmt


async def listar_terceros(
    session: AsyncSession,
    *,
    q: str | None = None,
    rol: str | None = None,
    activo: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Tercero], int]:
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)

    base = select(Tercero).where(Tercero.organization_id.in_(ids_visibles))
    base = _filtrar(base, q, rol, activo)
    if creado_por_subject is not None:
        base = base.where(Tercero.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    rows = await session.execute(
        base.order_by(Tercero.razon_social).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def obtener_tercero(session: AsyncSession, tercero_id: uuid.UUID) -> Tercero | None:
    """SOLO organización propia — uso interno de altas/ediciones/bajas. Para
    mostrar un tercero (posiblemente compartido) al leer, usar
    `obtener_tercero_visible`."""
    org_id = require_organization_id()
    return await session.scalar(
        select(Tercero)
        .options(selectinload(Tercero.contactos))
        .where(Tercero.id == tercero_id, Tercero.organization_id == org_id)
    )


async def obtener_tercero_visible(session: AsyncSession, tercero_id: uuid.UUID) -> Tercero | None:
    """Para mostrar el detalle: propia organización o, si la cuenta
    comparte maestros, también el de una organización hermana."""
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    return await session.scalar(
        select(Tercero)
        .options(selectinload(Tercero.contactos))
        .where(Tercero.id == tercero_id, Tercero.organization_id.in_(ids_visibles))
    )


async def crear_tercero(session: AsyncSession, datos: TerceroCreate) -> Tercero:
    org_id = require_organization_id()
    codigo = datos.codigo or await siguiente_codigo(session)

    existe = await session.scalar(
        select(Tercero.id).where(
            Tercero.organization_id == org_id, Tercero.codigo == codigo
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe un tercero con el código '{codigo}'")

    payload = datos.model_dump(exclude={"codigo", "contactos"})
    tercero = Tercero(organization_id=org_id, codigo=codigo, **payload, **datos_autoria())
    session.add(tercero)
    await session.flush()

    for contacto in datos.contactos:
        session.add(
            Contacto(
                organization_id=org_id,
                tercero_id=tercero.id,
                **contacto.model_dump(),
                **datos_autoria(),
            )
        )
    await session.flush()
    await session.refresh(tercero, attribute_names=["contactos"])
    return tercero


async def actualizar_tercero(
    session: AsyncSession, tercero_id: uuid.UUID, datos: TerceroUpdate
) -> Tercero | None:
    tercero = await obtener_tercero(session, tercero_id)
    if tercero is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(tercero, campo, valor)
    await session.flush()
    return tercero


async def eliminar_tercero(session: AsyncSession, tercero_id: uuid.UUID) -> bool:
    tercero = await obtener_tercero(session, tercero_id)
    if tercero is None:
        return False
    await session.delete(tercero)
    await session.flush()
    return True


# --- Contactos ---


async def listar_contactos(
    session: AsyncSession,
    *,
    tercero_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Contacto], int]:
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    base = select(Contacto).where(Contacto.organization_id.in_(ids_visibles))
    if tercero_id is not None:
        base = base.where(Contacto.tercero_id == tercero_id)
    if creado_por_subject is not None:
        base = base.where(Contacto.creado_por_subject == creado_por_subject)
    if q:
        patron = f"%{q}%"
        base = base.where(
            or_(
                Contacto.nombre.ilike(patron),
                Contacto.apellidos.ilike(patron),
                Contacto.email.ilike(patron),
            )
        )

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    rows = await session.execute(
        base.order_by(Contacto.nombre).limit(limit).offset(offset)
    )
    return list(rows.scalars()), int(total or 0)


async def obtener_contacto(
    session: AsyncSession, contacto_id: uuid.UUID
) -> Contacto | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Contacto).where(
            Contacto.id == contacto_id, Contacto.organization_id == org_id
        )
    )


async def crear_contacto(
    session: AsyncSession, datos: ContactoCreate | ContactoBase, *, tercero_id: uuid.UUID | None = None
) -> Contacto:
    org_id = require_organization_id()
    payload = datos.model_dump()
    payload["tercero_id"] = tercero_id or payload.get("tercero_id")
    contacto = Contacto(organization_id=org_id, **payload, **datos_autoria())
    session.add(contacto)
    await session.flush()
    return contacto


async def actualizar_contacto(
    session: AsyncSession, contacto_id: uuid.UUID, datos: ContactoUpdate
) -> Contacto | None:
    contacto = await obtener_contacto(session, contacto_id)
    if contacto is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(contacto, campo, valor)
    await session.flush()
    return contacto


async def eliminar_contacto(session: AsyncSession, contacto_id: uuid.UUID) -> bool:
    contacto = await obtener_contacto(session, contacto_id)
    if contacto is None:
        return False
    await session.delete(contacto)
    await session.flush()
    return True


# --- Contactos asociados (Fase 28) ---


async def listar_asociados(
    session: AsyncSession, entidad: EntidadContacto, entidad_id: uuid.UUID
) -> list[ContactoAsociado]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(ContactoAsociado)
        .options(selectinload(ContactoAsociado.contacto))
        .where(
            ContactoAsociado.organization_id == org_id,
            ContactoAsociado.entidad == entidad,
            ContactoAsociado.entidad_id == entidad_id,
        )
        .order_by(ContactoAsociado.created_at)
    )
    return list(filas.scalars())


async def asociar_contacto(
    session: AsyncSession,
    entidad: EntidadContacto,
    entidad_id: uuid.UUID,
    datos: ContactoAsociadoCreate,
) -> ContactoAsociado:
    org_id = require_organization_id()
    existe = await session.scalar(
        select(ContactoAsociado.id).where(
            ContactoAsociado.organization_id == org_id,
            ContactoAsociado.entidad == entidad,
            ContactoAsociado.entidad_id == entidad_id,
            ContactoAsociado.contacto_id == datos.contacto_id,
        )
    )
    if existe:
        raise AsociacionDuplicada("Ese contacto ya está asociado a este registro")

    asociado = ContactoAsociado(
        organization_id=org_id,
        entidad=entidad,
        entidad_id=entidad_id,
        contacto_id=datos.contacto_id,
        rol=datos.rol,
        **datos_autoria(),
    )
    session.add(asociado)
    await session.flush()
    await session.refresh(asociado, attribute_names=["contacto"])
    return asociado


async def eliminar_asociacion(session: AsyncSession, asociacion_id: uuid.UUID) -> bool:
    org_id = require_organization_id()
    asociado = await session.scalar(
        select(ContactoAsociado).where(
            ContactoAsociado.id == asociacion_id, ContactoAsociado.organization_id == org_id
        )
    )
    if asociado is None:
        return False
    await session.delete(asociado)
    await session.flush()
    return True
