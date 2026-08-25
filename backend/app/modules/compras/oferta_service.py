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
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrigenDato
from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import require_organization_id
from app.modules.compras.models import (
    EstadoDestinatario,
    OfertaLinea,
    SolicitudDestinatario,
    SolicitudLinea,
    SolicitudPrecios,
)
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


async def cerrar_oferta(
    session: AsyncSession,
    solicitud: SolicitudPrecios,
    destinatario: SolicitudDestinatario,
    *,
    proveedor_nombre: str,
) -> Presupuesto:
    """Genera el presupuesto-oferta de UN proveedor a partir de lo que ha
    rellenado. Idempotente: si ya cerró, devuelve el mismo presupuesto en vez
    de crear otro — cerrar dos veces no debe duplicar nada ni quemar dos
    números de serie.

    Solo entran las líneas que ÉL ha cotizado: si el paquete creció después de
    mandárselo, las que no llegó a ver simplemente no están en su oferta."""
    if destinatario.oferta_presupuesto_id is not None:
        existente = await session.scalar(
            select(Presupuesto).where(Presupuesto.id == destinatario.oferta_presupuesto_id)
        )
        if existente is not None:
            return existente

    org_id = require_organization_id()

    filas = (
        await session.execute(
            select(SolicitudLinea, OfertaLinea)
            .join(
                OfertaLinea,
                (OfertaLinea.linea_id == SolicitudLinea.id)
                & (OfertaLinea.destinatario_id == destinatario.id),
            )
            .where(
                SolicitudLinea.solicitud_id == solicitud.id,
                OfertaLinea.precio_ofertado.is_not(None),
            )
            .order_by(SolicitudLinea.orden)
        )
    ).all()
    if not filas:
        raise SinLineasConPrecio("El proveedor no ha puesto precio a ninguna línea")
    con_precio = [(linea, oferta) for linea, oferta in filas]

    # Se atribuye al usuario que la envió, no al proveedor: `AutoriaMixin`
    # con el subject sintético dejaría la oferta invisible para su propio
    # destinatario en cuanto tuviera el permiso "solo los míos" — es él quien
    # tiene que verla y decidir sobre ella, no quien la rellenó desde fuera.
    presupuesto = Presupuesto(
        organization_id=org_id,
        codigo=await _codigo_oferta_libre(session, org_id),
        nombre=f"Oferta de {proveedor_nombre} — {solicitud.titulo}",
        tipo=TipoPresupuesto.PROVEEDOR,
        proveedor_id=destinatario.proveedor_id,
        creado_por_subject=solicitud.emisor_subject,
        creado_por_nombre=solicitud.emisor_nombre,
    )
    session.add(presupuesto)
    await session.flush()

    # Un capítulo por cada capítulo de origen, en el mismo orden en que
    # aparecen las líneas — no hay que reordenar nada porque ya vinieron
    # ordenadas por capítulo al congelarlas en `crear_solicitud`.
    por_capitulo: dict[str, list[tuple[SolicitudLinea, OfertaLinea]]] = defaultdict(list)
    for linea, oferta in con_precio:
        por_capitulo[linea.capitulo_resumen or "Sin capítulo"].append((linea, oferta))

    for capitulo_resumen, lineas_capitulo in por_capitulo.items():
        capitulo = await service.crear_capitulo(
            session, presupuesto.id, CapituloCreate(resumen=capitulo_resumen)
        )
        assert capitulo is not None
        for linea, oferta in lineas_capitulo:
            await service.crear_partida(
                session,
                capitulo.id,
                PartidaCreate(
                    resumen=linea.resumen,
                    texto=linea.texto,
                    unidad=linea.unidad,
                    precio=oferta.precio_ofertado,
                    lineas=[LineaMedicionCreate(uds=linea.medicion)],
                ),
            )

    destinatario.oferta_presupuesto_id = presupuesto.id
    destinatario.estado = EstadoDestinatario.RESPONDIDA
    destinatario.respondida_en = datetime.now(UTC)
    await session.flush()
    return presupuesto


async def aprobar_linea(
    session: AsyncSession,
    oferta: OfertaLinea,
    linea: SolicitudLinea,
    destinatario: SolicitudDestinatario,
    solicitud: SolicitudPrecios,
) -> Partida:
    """Adjudica esta línea a este proveedor y aplica su precio sobre la
    partida ORIGINAL (no sobre la del presupuesto-oferta) — mismo patrón que
    "Cambiar por banco de precios" (Fase 52).

    Una línea se adjudica a UN proveedor: si ya se le dio a otro, se rechaza
    en vez de reescribir el descompuesto por segunda vez sin rastro de cuál
    manda."""
    if oferta.precio_ofertado is None:
        raise LineaSinPrecio("Esta línea no tiene precio ofertado")
    if linea.adjudicada_a_id is not None:
        if linea.adjudicada_a_id == destinatario.id:
            raise LineaYaAprobada("Esta línea ya estaba adjudicada a este proveedor")
        otro = await session.scalar(
            select(Tercero.razon_social)
            .select_from(SolicitudDestinatario)
            .join(Tercero, Tercero.id == SolicitudDestinatario.proveedor_id)
            .where(SolicitudDestinatario.id == linea.adjudicada_a_id)
        )
        raise LineaYaAprobada(
            f"Esta línea ya se adjudicó a «{otro or 'otro proveedor'}»"
        )
    if linea.partida_id is None:
        raise LineaSinPrecio("La partida original de esta línea ya no existe")

    org_id = require_organization_id()
    partida = await service.obtener_partida(session, linea.partida_id)
    if partida is None:
        raise LineaSinPrecio("La partida original de esta línea ya no existe")

    proveedor = await session.scalar(
        select(Tercero).where(
            Tercero.id == destinatario.proveedor_id, Tercero.organization_id == org_id
        )
    )
    proveedor_nombre = proveedor.razon_social if proveedor else "proveedor"

    if linea.concepto_id is not None:
        # La línea pedía UN componente del descompuesto (solo el material,
        # solo la mano de obra…): no se sustituye nada, solo se le pone al
        # componente el precio que ha dado el proveedor. `cambiar_precio_
        # componente` ya independiza el descompuesto del banco al tocarlo, que
        # es exactamente lo que hay que hacer — el banco no se toca desde
        # aquí, arrastraría a otros presupuestos.
        #
        # Alcance `partida` a propósito: aprobar una oferta es una decisión
        # sobre ESTA partida. Que el precio quede disponible en otras es lo
        # que resuelve el `PrecioSuministro` de más abajo, sin reescribirles
        # nada por la espalda.
        afectadas = await service.cambiar_precio_componente(
            session, partida.id, linea.concepto_id, oferta.precio_ofertado, "partida"
        )
        if afectadas == 0:
            raise LineaSinPrecio(
                "Ese componente ya no está en el descompuesto de la partida"
            )
        concepto_id = linea.concepto_id
    else:
        concepto = await banco_service.crear_concepto(
            session,
            ConceptoCreate(
                tipo=TipoConcepto.BASICO,
                naturaleza=NaturalezaConcepto.SERVICIO,
                unidad=partida.unidad,
                resumen=f"Subcontrata {proveedor_nombre} — {linea.resumen}"[:250],
                precio=oferta.precio_ofertado,
                origen_precio="manual",
                origen_dato=OrigenDato.IMPORTADO,
            ),
        )
        await service._vaciar_descomposicion_propia(session, partida.id)  # noqa: SLF001
        await service.anadir_componente(
            session, partida.id, concepto.id, Decimal("1"), Decimal("1")
        )
        concepto_id = concepto.id

    # Registro de precio de proveedor (Fase de banco de precios): deja el
    # precio disponible para futuros presupuestos vía `calculo.precio_
    # referencia`, no solo aplicado en esta partida.
    session.add(
        PrecioSuministro(
            organization_id=org_id,
            concepto_id=concepto_id,
            proveedor_id=destinatario.proveedor_id,
            precio=oferta.precio_ofertado,
            vigente_desde=date.today(),
            es_preferente=False,
            origen_dato=OrigenDato.IMPORTADO,
            notas=f"Solicitud {solicitud.codigo} — {solicitud.titulo}",
        )
    )

    oferta.aprobada = True
    linea.adjudicada_a_id = destinatario.id
    await session.flush()
    return partida
