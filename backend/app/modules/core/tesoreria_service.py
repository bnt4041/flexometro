import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.core.tesoreria_models import CuentaFinanciera
from app.modules.core.tesoreria_schemas import CuentaFinancieraCreate, CuentaFinancieraUpdate


class NombreDuplicado(Exception):
    pass


class CuentaNoEncontrada(Exception):
    pass


class CuentaEnUso(Exception):
    pass


async def listar(session: AsyncSession, *, solo_activas: bool = False) -> list[CuentaFinanciera]:
    org_id = require_organization_id()
    condiciones = [CuentaFinanciera.organization_id == org_id]
    if solo_activas:
        condiciones.append(CuentaFinanciera.activa.is_(True))
    filas = await session.execute(
        select(CuentaFinanciera)
        .where(*condiciones)
        # La predeterminada primero: es la que se elige sola al cobrar.
        .order_by(CuentaFinanciera.es_predeterminada.desc(), CuentaFinanciera.nombre)
    )
    return list(filas.scalars())


async def obtener(session: AsyncSession, cuenta_id: uuid.UUID) -> CuentaFinanciera | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(CuentaFinanciera).where(
            CuentaFinanciera.id == cuenta_id, CuentaFinanciera.organization_id == org_id
        )
    )


async def predeterminada(session: AsyncSession) -> CuentaFinanciera | None:
    """La que se imprime en presupuestos y facturas cuando la plantilla no
    pide una en concreto."""
    org_id = require_organization_id()
    return await session.scalar(
        select(CuentaFinanciera).where(
            CuentaFinanciera.organization_id == org_id,
            CuentaFinanciera.es_predeterminada.is_(True),
            CuentaFinanciera.activa.is_(True),
        )
    )


async def _quitar_predeterminada(session: AsyncSession, excepto: uuid.UUID | None = None) -> None:
    """Solo una predeterminada por organización: al marcar una, se desmarca
    la anterior en la misma sentencia."""
    org_id = require_organization_id()
    condiciones = [
        CuentaFinanciera.organization_id == org_id,
        CuentaFinanciera.es_predeterminada.is_(True),
    ]
    if excepto is not None:
        condiciones.append(CuentaFinanciera.id != excepto)
    await session.execute(
        update(CuentaFinanciera).where(*condiciones).values(es_predeterminada=False)
    )


async def crear(session: AsyncSession, datos: CuentaFinancieraCreate) -> CuentaFinanciera:
    org_id = require_organization_id()
    if datos.es_predeterminada:
        await _quitar_predeterminada(session)

    cuenta = CuentaFinanciera(
        organization_id=org_id, **datos.model_dump(), **datos_autoria()
    )
    session.add(cuenta)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise NombreDuplicado(f"Ya existe una cuenta llamada «{datos.nombre}»") from exc
    return cuenta


async def actualizar(
    session: AsyncSession, cuenta_id: uuid.UUID, datos: CuentaFinancieraUpdate
) -> CuentaFinanciera:
    cuenta = await obtener(session, cuenta_id)
    if cuenta is None:
        raise CuentaNoEncontrada("Cuenta no encontrada")

    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("es_predeterminada"):
        await _quitar_predeterminada(session, excepto=cuenta_id)

    for campo, valor in cambios.items():
        setattr(cuenta, campo, valor)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise NombreDuplicado(f"Ya existe una cuenta llamada «{cambios.get('nombre')}»") from exc
    return cuenta


async def eliminar(session: AsyncSession, cuenta_id: uuid.UUID) -> None:
    """No se borra si tiene cobros apuntando: se perdería el rastro de por
    dónde entró ese dinero. Para retirarla de circulación está `activa`."""
    from app.modules.facturacion.models import Cobro

    cuenta = await obtener(session, cuenta_id)
    if cuenta is None:
        raise CuentaNoEncontrada("Cuenta no encontrada")

    en_uso = await session.scalar(
        select(Cobro.id).where(Cobro.cuenta_financiera_id == cuenta_id).limit(1)
    )
    if en_uso:
        raise CuentaEnUso(
            "Esta cuenta tiene cobros registrados: desactívala en vez de borrarla"
        )

    await session.delete(cuenta)
    await session.flush()
