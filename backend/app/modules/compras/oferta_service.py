"""Dos momentos de una solicitud de precios que escriben en `presupuestos`:

- `cerrar_solicitud`: el proveedor termina de rellenar la separata y se
  genera su presupuesto-oferta (mismo paradigma de capítulos/partidas/
  mediciones que uno de cliente, distinguido por `tipo`).
- `aprobar_linea`: el emisor, desde el comparativo, elige una oferta para una
  partida — sustituye su descompuesto por la subcontrata de ese proveedor,
  igual que ya hace "Cambiar por banco de precios" (Fase 52).
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrigenDato
from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import require_organization_id
from app.modules.compras.models import EstadoSolicitud, SolicitudLinea, SolicitudPrecios
from app.modules.presupuestos import presupuesto_service as service
from app.modules.presupuestos import service as banco_service
from app.modules.presupuestos.models import NaturalezaConcepto, PrecioSuministro, TipoConcepto
from app.modules.presupuestos.models_presupuesto import Partida, Presupuesto, TipoPresupuesto
from app.modules.presupuestos.presupuesto_schemas import (
    CapituloCreate,
    LineaMedicionCreate,
    PartidaCreate,
)
from app.modules.presupuestos.schemas import ConceptoCreate
from app.modules.terceros.models import Tercero


class SinLineasConPrecio(Exception):
    pass


class LineaSinPrecio(Exception):
    pass


class LineaYaAprobada(Exception):
    pass


async def _codigo_oferta_libre(session: AsyncSession, org_id: uuid.UUID) -> str:
    async def existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(Presupuesto.id).where(
                    Presupuesto.organization_id == org_id, Presupuesto.codigo == codigo
                )
            )
        ) is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento="oferta_proveedor", existe=existe
    )


async def cerrar_solicitud(
    session: AsyncSession, solicitud: SolicitudPrecios, *, proveedor_nombre: str
) -> Presupuesto:
    """Genera el presupuesto-oferta a partir de lo que el proveedor ha
    rellenado. Idempotente: si ya se cerró, devuelve el mismo presupuesto en
    vez de crear otro — cerrar dos veces no debe duplicar nada ni quemar dos
    números de serie."""
    if solicitud.oferta_presupuesto_id is not None:
        existente = await session.scalar(
            select(Presupuesto).where(Presupuesto.id == solicitud.oferta_presupuesto_id)
        )
        if existente is not None:
            return existente

    org_id = require_organization_id()

    lineas = (
        await session.execute(
            select(SolicitudLinea)
            .where(SolicitudLinea.solicitud_id == solicitud.id)
            .order_by(SolicitudLinea.orden)
        )
    ).scalars().all()
    con_precio = [linea for linea in lineas if linea.precio_ofertado is not None]
    if not con_precio:
        raise SinLineasConPrecio("El proveedor no ha puesto precio a ninguna línea")

    # Se atribuye al usuario que la envió, no al proveedor: `AutoriaMixin`
    # con el subject sintético dejaría la oferta invisible para su propio
    # destinatario en cuanto tuviera el permiso "solo los míos" — es él quien
    # tiene que verla y decidir sobre ella, no quien la rellenó desde fuera.
    presupuesto = Presupuesto(
        organization_id=org_id,
        codigo=await _codigo_oferta_libre(session, org_id),
        nombre=f"Oferta de {proveedor_nombre} — {solicitud.codigo}",
        tipo=TipoPresupuesto.PROVEEDOR,
        proveedor_id=solicitud.proveedor_id,
        creado_por_subject=solicitud.emisor_subject,
        creado_por_nombre=solicitud.emisor_nombre,
    )
    session.add(presupuesto)
    await session.flush()

    # Un capítulo por cada capítulo de origen, en el mismo orden en que
    # aparecen las líneas — no hay que reordenar nada porque ya vinieron
    # ordenadas por capítulo al congelarlas en `crear_solicitud`.
    por_capitulo: dict[str, list[SolicitudLinea]] = defaultdict(list)
    for linea in con_precio:
        por_capitulo[linea.capitulo_resumen or "Sin capítulo"].append(linea)

    for capitulo_resumen, lineas_capitulo in por_capitulo.items():
        capitulo = await service.crear_capitulo(
            session, presupuesto.id, CapituloCreate(resumen=capitulo_resumen)
        )
        assert capitulo is not None
        for linea in lineas_capitulo:
            await service.crear_partida(
                session,
                capitulo.id,
                PartidaCreate(
                    resumen=linea.resumen,
                    texto=linea.texto,
                    unidad=linea.unidad,
                    precio=linea.precio_ofertado,
                    lineas=[LineaMedicionCreate(uds=linea.medicion)],
                ),
            )

    solicitud.oferta_presupuesto_id = presupuesto.id
    solicitud.estado = EstadoSolicitud.RESPONDIDA
    await session.flush()
    return presupuesto


async def aprobar_linea(
    session: AsyncSession, linea: SolicitudLinea, solicitud: SolicitudPrecios
) -> Partida:
    """Sustituye el descompuesto de la partida ORIGINAL (no la de la oferta)
    por la subcontrata de este proveedor a su precio — mismo patrón que
    "Cambiar por banco de precios" (Fase 52), con un paso previo: aquí el
    concepto de la subcontrata todavía no existe, hay que darlo de alta."""
    if linea.precio_ofertado is None:
        raise LineaSinPrecio("Esta línea no tiene precio ofertado")
    if linea.aprobada:
        raise LineaYaAprobada("Esta línea ya estaba aprobada")
    if linea.partida_id is None:
        raise LineaSinPrecio("La partida original de esta línea ya no existe")

    org_id = require_organization_id()
    partida = await service.obtener_partida(session, linea.partida_id)
    if partida is None:
        raise LineaSinPrecio("La partida original de esta línea ya no existe")

    proveedor = await session.scalar(
        select(Tercero).where(Tercero.id == solicitud.proveedor_id, Tercero.organization_id == org_id)
    )
    proveedor_nombre = proveedor.razon_social if proveedor else "proveedor"

    concepto = await banco_service.crear_concepto(
        session,
        ConceptoCreate(
            tipo=TipoConcepto.BASICO,
            naturaleza=NaturalezaConcepto.SERVICIO,
            unidad=partida.unidad,
            resumen=f"Subcontrata {proveedor_nombre} — {linea.resumen}"[:250],
            precio=linea.precio_ofertado,
            origen_precio="manual",
            origen_dato=OrigenDato.IMPORTADO,
        ),
    )

    await service._vaciar_descomposicion_propia(session, partida.id)  # noqa: SLF001
    await service.anadir_componente(session, partida.id, concepto.id, Decimal("1"), Decimal("1"))

    # Registro de precio de proveedor (Fase de banco de precios): deja el
    # precio disponible para futuros presupuestos vía `calculo.precio_
    # referencia`, no solo aplicado en esta partida.
    session.add(
        PrecioSuministro(
            organization_id=org_id,
            concepto_id=concepto.id,
            proveedor_id=solicitud.proveedor_id,
            precio=linea.precio_ofertado,
            vigente_desde=date.today(),
            es_preferente=False,
            origen_dato=OrigenDato.IMPORTADO,
            notas=f"Solicitud {solicitud.codigo}",
        )
    )

    linea.aprobada = True
    await session.flush()

    otras_pendientes = any(
        not otra.aprobada
        for otra in (
            await session.execute(
                select(SolicitudLinea).where(SolicitudLinea.solicitud_id == solicitud.id)
            )
        ).scalars()
        if otra.precio_ofertado is not None
    )
    if not otras_pendientes:
        solicitud.estado = EstadoSolicitud.APROBADA
        await session.flush()

    return partida
