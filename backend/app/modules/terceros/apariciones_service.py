"""Dónde aparece un tercero (Fase 46): la pestaña "Apariciones" de su ficha.

Cruza los cuatro módulos que guardan una referencia directa a `Tercero`
(presupuesto.cliente_id, albaran.proveedor_id, factura.cliente_id,
precio_suministro.proveedor_id) más las obras, que no referencian al tercero
directamente sino a través de su presupuesto.

Vive en `terceros` y no en un módulo aparte porque es estrictamente una
consulta de lectura sobre datos de otros módulos, sin escritura ni reglas de
negocio propias — igual que `documentos.buscar_documentos` cruza módulos
para el buscador de adjuntos.

Todo se filtra solo por RLS (la organización activa de la sesión): un
tercero compartido entre empresas de la misma cuenta puede aparecer en
presupuestos de la otra empresa, pero esta vista no los cruza — igual que el
resto de la aplicación, lo que se ve es lo de la empresa activa.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.terceros.apariciones_schemas import AparicionOut, TipoAparicion


async def apariciones_de(session: AsyncSession, tercero_id: uuid.UUID) -> list[AparicionOut]:
    from app.modules.compras.models import Albaran
    from app.modules.facturacion.models import Factura
    from app.modules.obras.models import Obra
    from app.modules.presupuestos.models import Concepto, PrecioSuministro
    from app.modules.presupuestos.models_presupuesto import Presupuesto

    resultado: list[AparicionOut] = []

    presupuestos = list(
        (
            await session.execute(
                select(Presupuesto)
                .where(Presupuesto.cliente_id == tercero_id)
                .order_by(Presupuesto.codigo.desc())
            )
        ).scalars()
    )
    for p in presupuestos:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.PRESUPUESTO,
                id=str(p.id),
                codigo=p.codigo,
                titulo=p.nombre,
                estado=p.estado.value,
            )
        )

    # No hay `obra.cliente_id`: una obra hereda el cliente de su presupuesto,
    # así que el cruce pasa por él.
    if presupuestos:
        obras = list(
            (
                await session.execute(
                    select(Obra).where(
                        Obra.presupuesto_id.in_([p.id for p in presupuestos])
                    )
                )
            ).scalars()
        )
        for o in obras:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.OBRA,
                    id=str(o.id),
                    codigo=o.codigo,
                    titulo=o.nombre,
                    estado=o.estado.value,
                )
            )

    albaranes = list(
        (
            await session.execute(
                select(Albaran)
                .where(Albaran.proveedor_id == tercero_id)
                .order_by(Albaran.fecha.desc())
            )
        ).scalars()
    )
    for a in albaranes:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.ALBARAN,
                id=str(a.id),
                codigo=a.codigo,
                titulo=a.numero_proveedor or a.codigo,
                subtitulo=a.fecha.isoformat(),
                estado=a.estado.value,
            )
        )

    facturas = list(
        (
            await session.execute(
                select(Factura)
                .where(Factura.cliente_id == tercero_id)
                .order_by(Factura.codigo.desc())
            )
        ).scalars()
    )
    for f in facturas:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.FACTURA,
                id=str(f.id),
                codigo=f.codigo,
                titulo=f.concepto,
                estado=f.estado.value,
            )
        )

    # Como proveedor de una tarifa en el banco de precios — no es una "ficha"
    # en el sentido de las demás, pero es tan aparición como cualquier otra:
    # borrar el tercero rompería esta tarifa igual que rompería un albarán.
    precios = list(
        (
            await session.execute(
                select(PrecioSuministro, Concepto)
                .join(Concepto, Concepto.id == PrecioSuministro.concepto_id)
                .where(PrecioSuministro.proveedor_id == tercero_id)
                .order_by(Concepto.codigo)
            )
        ).all()
    )
    for precio, concepto in precios:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.CONCEPTO,
                id=str(concepto.id),
                codigo=concepto.codigo,
                titulo=concepto.resumen,
                subtitulo=f"{precio.precio} €/{concepto.unidad}"
                + (" · preferente" if precio.es_preferente else ""),
            )
        )

    return resultado
