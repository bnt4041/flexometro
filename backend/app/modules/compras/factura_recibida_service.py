"""Registro de facturas de proveedor.

Deliberadamente sencillo: **estas facturas no las emitimos nosotros**, así que
no hay serie, ni numeración legal, ni circuito Veri*Factu. Lo que hay es lo que
hace falta para controlar la obra y no pagar dos veces: quién factura, cuánto,
a qué obra, con qué vencimiento, si está pagada, y qué albaranes cubre.

El total llega materializado desde quien registra y se comprueba, no se impone:
si el proveedor redondea de otra forma, manda el papel. Ver `_cuadrar_importes`.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import TIPO_IVA_PORCENTAJE, TipoIVA
from app.core.numeracion import siguiente_referencia_libre
from app.core.redondeo import redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.compras.models import (
    Albaran,
    EstadoFacturaRecibida,
    FacturaRecibida,
    FacturaRecibidaAlbaran,
)

TIPO_DOCUMENTO = "factura_recibida"


class FacturaInvalida(Exception):
    pass


class AlbaranInvalido(Exception):
    pass


def cuota_de(base: Decimal, tipo_iva: TipoIVA, inversion_sujeto_pasivo: bool) -> Decimal:
    """Misma regla que en facturación de venta: con inversión del sujeto
    pasivo la cuota es cero y la autorrepercutimos nosotros."""
    if inversion_sujeto_pasivo:
        return Decimal("0.00")
    porcentaje = Decimal(TIPO_IVA_PORCENTAJE[tipo_iva])
    return redondear_precio(base * porcentaje / Decimal("100"))


def _cuadrar_importes(
    base: Decimal,
    tipo_iva: TipoIVA,
    isp: bool,
    cuota_dada: Decimal | None,
    total_dado: Decimal | None,
) -> tuple[Decimal, Decimal]:
    """Devuelve (cuota, total).

    Si quien registra teclea la cuota o el total, manda lo tecleado: es lo que
    dice el papel, y un céntimo de diferencia por redondeo del proveedor no
    puede impedir registrar su factura. Solo se calcula lo que no se dio.
    """
    cuota = cuota_dada if cuota_dada is not None else cuota_de(base, tipo_iva, isp)
    total = total_dado if total_dado is not None else redondear_precio(base + cuota)
    return cuota, total


async def siguiente_codigo(session: AsyncSession) -> str:
    org_id = require_organization_id()

    async def existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(FacturaRecibida.id).where(
                    FacturaRecibida.organization_id == org_id,
                    FacturaRecibida.codigo == codigo,
                )
            )
        ) is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento=TIPO_DOCUMENTO, existe=existe
    )


async def _validar_albaranes(
    session: AsyncSession, obra_id: uuid.UUID, albaran_ids: list[uuid.UUID]
) -> None:
    """Los albaranes tienen que ser de ESTA obra.

    Los ids llegan del cliente: sin comprobarlo se podría colgar de una factura
    un albarán de otra obra y descuadrar las dos.
    """
    if not albaran_ids:
        return
    org_id = require_organization_id()
    validos = set(
        (
            await session.execute(
                select(Albaran.id).where(
                    Albaran.id.in_(albaran_ids),
                    Albaran.obra_id == obra_id,
                    Albaran.organization_id == org_id,
                )
            )
        )
        .scalars()
        .all()
    )
    faltan = set(albaran_ids) - validos
    if faltan:
        raise AlbaranInvalido(
            "Alguno de los albaranes no existe o no es de esta obra"
        )


async def crear(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    numero_proveedor: str,
    fecha: date,
    base_imponible: Decimal,
    tipo_iva: TipoIVA = TipoIVA.GENERAL,
    inversion_sujeto_pasivo: bool = False,
    cuota_iva: Decimal | None = None,
    total: Decimal | None = None,
    fecha_vencimiento: date | None = None,
    notas: str | None = None,
    albaran_ids: list[uuid.UUID] | None = None,
) -> FacturaRecibida:
    from app.modules.compras.service import _validar_obra, _validar_proveedor

    await _validar_obra(session, obra_id)
    await _validar_proveedor(session, proveedor_id)
    albaran_ids = albaran_ids or []
    await _validar_albaranes(session, obra_id, albaran_ids)

    numero = numero_proveedor.strip()
    if not numero:
        raise FacturaInvalida("La factura del proveedor tiene que traer su número")

    org_id = require_organization_id()
    cuota, importe_total = _cuadrar_importes(
        base_imponible, tipo_iva, inversion_sujeto_pasivo, cuota_iva, total
    )

    ya = await session.scalar(
        select(FacturaRecibida.codigo).where(
            FacturaRecibida.organization_id == org_id,
            FacturaRecibida.proveedor_id == proveedor_id,
            FacturaRecibida.numero_proveedor == numero,
        )
    )
    if ya:
        raise FacturaInvalida(
            f"Este proveedor ya tiene registrada la factura {numero} (es {ya})"
        )

    factura = FacturaRecibida(
        organization_id=org_id,
        codigo=await siguiente_codigo(session),
        numero_proveedor=numero,
        obra_id=obra_id,
        proveedor_id=proveedor_id,
        fecha=fecha,
        fecha_vencimiento=fecha_vencimiento,
        base_imponible=base_imponible,
        tipo_iva=tipo_iva,
        inversion_sujeto_pasivo=inversion_sujeto_pasivo,
        cuota_iva=cuota,
        total=importe_total,
        estado=EstadoFacturaRecibida.PENDIENTE,
        notas=notas,
        **datos_autoria(),
    )
    session.add(factura)
    await session.flush()

    for albaran_id in albaran_ids:
        session.add(
            FacturaRecibidaAlbaran(
                organization_id=org_id, factura_id=factura.id, albaran_id=albaran_id
            )
        )
    await session.flush()
    return factura


async def listar(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    estado: EstadoFacturaRecibida | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FacturaRecibida], int]:
    consulta = select(FacturaRecibida).options(
        selectinload(FacturaRecibida.albaranes)
    )
    condiciones = []
    if obra_id is not None:
        condiciones.append(FacturaRecibida.obra_id == obra_id)
    if proveedor_id is not None:
        condiciones.append(FacturaRecibida.proveedor_id == proveedor_id)
    if estado is not None:
        condiciones.append(FacturaRecibida.estado == estado)
    if condiciones:
        consulta = consulta.where(*condiciones)

    total = await session.scalar(
        select(func.count()).select_from(FacturaRecibida).where(*condiciones)
        if condiciones
        else select(func.count()).select_from(FacturaRecibida)
    )
    filas = (
        await session.execute(
            consulta.order_by(FacturaRecibida.fecha.desc(), FacturaRecibida.codigo.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return list(filas), int(total or 0)


async def obtener(
    session: AsyncSession, factura_id: uuid.UUID
) -> FacturaRecibida | None:
    return await session.scalar(
        select(FacturaRecibida)
        .options(selectinload(FacturaRecibida.albaranes))
        .where(FacturaRecibida.id == factura_id)
    )


async def actualizar(
    session: AsyncSession, factura: FacturaRecibida, cambios: dict
) -> FacturaRecibida:
    """Edición campo a campo. Los importes se recuadran solo si cambia algo que
    los afecta, para no pisar un total tecleado a mano con nuestra aritmética."""
    albaran_ids = cambios.pop("albaran_ids", None)

    if "numero_proveedor" in cambios:
        numero = (cambios["numero_proveedor"] or "").strip()
        if not numero:
            raise FacturaInvalida("La factura del proveedor tiene que traer su número")
        cambios["numero_proveedor"] = numero

    afecta_importes = {"base_imponible", "tipo_iva", "inversion_sujeto_pasivo"}
    for campo, valor in cambios.items():
        setattr(factura, campo, valor)

    if afecta_importes & cambios.keys() and not ({"cuota_iva", "total"} & cambios.keys()):
        factura.cuota_iva = cuota_de(
            factura.base_imponible, factura.tipo_iva, factura.inversion_sujeto_pasivo
        )
        factura.total = redondear_precio(factura.base_imponible + factura.cuota_iva)

    # Pagarla pone la fecha si no se dio; despagarla la quita, para que no se
    # quede una fecha de pago en una factura pendiente.
    if cambios.get("estado") == EstadoFacturaRecibida.PAGADA and factura.fecha_pago is None:
        factura.fecha_pago = date.today()
    if cambios.get("estado") == EstadoFacturaRecibida.PENDIENTE:
        factura.fecha_pago = None

    if albaran_ids is not None:
        await _validar_albaranes(session, factura.obra_id, albaran_ids)
        await session.execute(
            delete(FacturaRecibidaAlbaran).where(
                FacturaRecibidaAlbaran.factura_id == factura.id
            )
        )
        org_id = require_organization_id()
        for albaran_id in albaran_ids:
            session.add(
                FacturaRecibidaAlbaran(
                    organization_id=org_id, factura_id=factura.id, albaran_id=albaran_id
                )
            )

    await session.flush()
    return factura


async def eliminar(session: AsyncSession, factura: FacturaRecibida) -> None:
    await session.delete(factura)
    await session.flush()


async def totales_de_obra(session: AsyncSession, obra_id: uuid.UUID) -> dict:
    """Lo facturado por proveedores en esta obra, y cuánto queda por pagar."""
    fila = (
        await session.execute(
            select(
                func.coalesce(func.sum(FacturaRecibida.base_imponible), 0),
                func.coalesce(func.sum(FacturaRecibida.total), 0),
                func.coalesce(
                    func.sum(FacturaRecibida.total).filter(
                        FacturaRecibida.estado == EstadoFacturaRecibida.PENDIENTE
                    ),
                    0,
                ),
            ).where(FacturaRecibida.obra_id == obra_id)
        )
    ).one()
    return {
        "base": Decimal(fila[0]),
        "total": Decimal(fila[1]),
        "pendiente_de_pago": Decimal(fila[2]),
    }


async def albaranes_sin_facturar(
    session: AsyncSession, obra_id: uuid.UUID
) -> list[uuid.UUID]:
    """Albaranes de la obra que no aparecen en ninguna factura recibida.

    Es la mitad útil del cuadre: material que entró y nadie ha facturado
    todavía. La otra mitad (facturas sin albarán) se ve en la propia lista.
    """
    facturados = select(FacturaRecibidaAlbaran.albaran_id).where(
        FacturaRecibidaAlbaran.albaran_id.is_not(None)
    )
    filas = (
        await session.execute(
            select(Albaran.id).where(
                Albaran.obra_id == obra_id, Albaran.id.not_in(facturados)
            )
        )
    ).scalars()
    return list(filas)
