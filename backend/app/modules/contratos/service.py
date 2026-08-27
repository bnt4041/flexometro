"""Contratos: formaliza el acuerdo de una obra, con cliente o con proveedor.

Sin líneas ni cálculo propio: el precio vive en el `Presupuesto` que enlaza
(si lo hay). Aquí solo se valida que el tercero indicado tenga el rol que
corresponde a `tipo`, y que la obra y el presupuesto (si se da) existan."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.contratos.models import Contrato, TipoContrato
from app.modules.contratos.schemas import ContratoCreate, ContratoUpdate

TIPO_DOCUMENTO = "contrato"


class CodigoDuplicado(Exception):
    pass


class ObraInvalida(Exception):
    pass


class TerceroInvalido(Exception):
    pass


class PresupuestoInvalido(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    org_id = require_organization_id()

    async def existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(Contrato.id).where(
                    Contrato.organization_id == org_id, Contrato.codigo == codigo
                )
            )
        ) is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento=TIPO_DOCUMENTO, existe=existe
    )


async def _validar_obra(session: AsyncSession, obra_id: uuid.UUID) -> None:
    from app.modules.obras.service import obtener_obra

    if await obtener_obra(session, obra_id) is None:
        raise ObraInvalida("La obra no existe en esta organización")


async def _validar_tercero(session: AsyncSession, tercero_id: uuid.UUID, tipo: TipoContrato) -> None:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    fila = await session.execute(
        select(Tercero.es_cliente, Tercero.es_proveedor).where(
            Tercero.id == tercero_id, Tercero.organization_id == org_id
        )
    )
    resultado = fila.first()
    if resultado is None:
        raise TerceroInvalido("El tercero indicado no existe en esta organización")
    es_cliente, es_proveedor = resultado
    if tipo == TipoContrato.CLIENTE and not es_cliente:
        raise TerceroInvalido("El tercero indicado no tiene el rol de cliente")
    if tipo == TipoContrato.PROVEEDOR and not es_proveedor:
        raise TerceroInvalido("El tercero indicado no tiene el rol de proveedor")


async def _validar_presupuesto(session: AsyncSession, presupuesto_id: uuid.UUID) -> None:
    from app.modules.presupuestos.models_presupuesto import Presupuesto

    org_id = require_organization_id()
    existe = await session.scalar(
        select(Presupuesto.id).where(
            Presupuesto.id == presupuesto_id, Presupuesto.organization_id == org_id
        )
    )
    if existe is None:
        raise PresupuestoInvalido("El presupuesto indicado no existe en esta organización")


async def crear(session: AsyncSession, datos: ContratoCreate) -> Contrato:
    org_id = require_organization_id()
    await _validar_obra(session, datos.obra_id)
    tercero_id = datos.cliente_id if datos.tipo == TipoContrato.CLIENTE else datos.proveedor_id
    assert tercero_id is not None  # ya garantizado por el validador del schema
    await _validar_tercero(session, tercero_id, datos.tipo)
    if datos.presupuesto_id is not None:
        await _validar_presupuesto(session, datos.presupuesto_id)

    async def _existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(Contrato.id).where(
                    Contrato.organization_id == org_id, Contrato.codigo == codigo
                )
            )
        ) is not None

    if datos.codigo:
        if await _existe(datos.codigo):
            raise CodigoDuplicado(f"Ya existe un contrato con el código '{datos.codigo}'")
        codigo = datos.codigo
    else:
        codigo = await siguiente_referencia_libre(
            session, organization_id=org_id, tipo_documento=TIPO_DOCUMENTO, existe=_existe
        )

    contrato = Contrato(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(contrato)
    await session.flush()
    return contrato


async def listar(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    tipo: TipoContrato | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[tuple[Contrato, str]], int]:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    base = (
        select(Contrato, Tercero.razon_social)
        .join(
            Tercero,
            Tercero.id == func.coalesce(Contrato.cliente_id, Contrato.proveedor_id),
        )
        .where(Contrato.organization_id == org_id)
    )
    if obra_id is not None:
        base = base.where(Contrato.obra_id == obra_id)
    if tipo is not None:
        base = base.where(Contrato.tipo == tipo)
    if creado_por_subject is not None:
        base = base.where(Contrato.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(
            base.with_only_columns(Contrato.id).order_by(None).subquery()
        )
    )
    filas = await session.execute(
        base.order_by(Contrato.fecha_firma.desc().nulls_last(), Contrato.codigo.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(filas.all()), int(total or 0)


async def obtener(session: AsyncSession, contrato_id: uuid.UUID) -> tuple[Contrato, str] | None:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    fila = (
        await session.execute(
            select(Contrato, Tercero.razon_social)
            .join(
                Tercero,
                Tercero.id == func.coalesce(Contrato.cliente_id, Contrato.proveedor_id),
            )
            .where(Contrato.id == contrato_id, Contrato.organization_id == org_id)
        )
    ).first()
    return tuple(fila) if fila else None


async def obtener_obj(session: AsyncSession, contrato_id: uuid.UUID) -> Contrato | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Contrato).where(Contrato.id == contrato_id, Contrato.organization_id == org_id)
    )


async def actualizar(
    session: AsyncSession, contrato_id: uuid.UUID, datos: ContratoUpdate
) -> Contrato | None:
    contrato = await obtener_obj(session, contrato_id)
    if contrato is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("presupuesto_id") is not None:
        await _validar_presupuesto(session, cambios["presupuesto_id"])
    for campo, valor in cambios.items():
        setattr(contrato, campo, valor)
    await session.flush()
    return contrato


async def eliminar(session: AsyncSession, contrato_id: uuid.UUID) -> bool:
    contrato = await obtener_obj(session, contrato_id)
    if contrato is None:
        return False
    await session.delete(contrato)
    await session.flush()
    return True
