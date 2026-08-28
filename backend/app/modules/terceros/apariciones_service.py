"""Dónde aparecen un tercero o un contacto (Fases 46/49): la pestaña
"Apariciones" de sus fichas.

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

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.terceros.apariciones_schemas import AparicionOut, TipoAparicion


async def apariciones_de(session: AsyncSession, tercero_id: uuid.UUID) -> list[AparicionOut]:
    from app.modules.compras.models import Albaran, FacturaRecibida, Pedido
    from app.modules.contratos.models import Contrato
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
                .where(or_(Albaran.proveedor_id == tercero_id, Albaran.cliente_id == tercero_id))
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

    pedidos = list(
        (
            await session.execute(
                select(Pedido)
                .where(or_(Pedido.proveedor_id == tercero_id, Pedido.cliente_id == tercero_id))
                .order_by(Pedido.fecha.desc())
            )
        ).scalars()
    )
    for pe in pedidos:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.PEDIDO,
                id=str(pe.id),
                codigo=pe.codigo,
                titulo=pe.codigo,
                subtitulo=pe.fecha.isoformat(),
                estado=pe.estado.value,
            )
        )

    facturas_recibidas = list(
        (
            await session.execute(
                select(FacturaRecibida)
                .where(FacturaRecibida.proveedor_id == tercero_id)
                .order_by(FacturaRecibida.fecha.desc())
            )
        ).scalars()
    )
    for fr in facturas_recibidas:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.FACTURA_RECIBIDA,
                id=str(fr.id),
                codigo=fr.codigo,
                titulo=fr.numero_proveedor,
                subtitulo=fr.fecha.isoformat(),
                estado=fr.estado.value,
            )
        )

    # Un contrato con este tercero, de cliente o de proveedor — según cuál de
    # las dos columnas coincida (nunca las dos a la vez, ver el validador del
    # schema en `contratos.schemas`).
    contratos = list(
        (
            await session.execute(
                select(Contrato)
                .where(or_(Contrato.cliente_id == tercero_id, Contrato.proveedor_id == tercero_id))
                .order_by(Contrato.codigo.desc())
            )
        ).scalars()
    )
    for c in contratos:
        resultado.append(
            AparicionOut(
                tipo=TipoAparicion.CONTRATO,
                id=str(c.id),
                codigo=c.codigo,
                titulo=c.codigo,
                subtitulo=c.fecha_firma.isoformat() if c.fecha_firma else None,
                estado=c.estado.value,
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


async def apariciones_de_contacto(session: AsyncSession, contacto_id: uuid.UUID) -> list[AparicionOut]:
    """A diferencia del tercero, un contacto no tiene columnas FK propias en
    ningún módulo: se vincula por `ContactoAsociado` (entidad/entidad_id
    genéricos, Fase 28), así que aquí no hay más remedio que agrupar por
    entidad y resolver cada tabla aparte."""
    from app.modules.compras.models import Albaran, FacturaRecibida, Pedido
    from app.modules.contratos.models import Contrato
    from app.modules.facturacion.models import Certificacion, Factura
    from app.modules.obras.models import Obra
    from app.modules.presupuestos.models_presupuesto import Presupuesto
    from app.modules.terceros.models import ContactoAsociado, EntidadContacto

    asociaciones = list(
        (
            await session.execute(
                select(ContactoAsociado).where(ContactoAsociado.contacto_id == contacto_id)
            )
        ).scalars()
    )
    ids_por_entidad: dict[EntidadContacto, set[uuid.UUID]] = {}
    for asociacion in asociaciones:
        ids_por_entidad.setdefault(asociacion.entidad, set()).add(asociacion.entidad_id)

    resultado: list[AparicionOut] = []

    presupuesto_ids = ids_por_entidad.get(EntidadContacto.PRESUPUESTO)
    if presupuesto_ids:
        filas = (
            await session.execute(select(Presupuesto).where(Presupuesto.id.in_(presupuesto_ids)))
        ).scalars()
        for p in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.PRESUPUESTO,
                    id=str(p.id),
                    codigo=p.codigo,
                    titulo=p.nombre,
                    estado=p.estado.value,
                )
            )

    obra_ids = ids_por_entidad.get(EntidadContacto.OBRA)
    if obra_ids:
        filas = (await session.execute(select(Obra).where(Obra.id.in_(obra_ids)))).scalars()
        for o in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.OBRA,
                    id=str(o.id),
                    codigo=o.codigo,
                    titulo=o.nombre,
                    estado=o.estado.value,
                )
            )

    certificacion_ids = ids_por_entidad.get(EntidadContacto.CERTIFICACION)
    if certificacion_ids:
        filas = (
            await session.execute(select(Certificacion).where(Certificacion.id.in_(certificacion_ids)))
        ).scalars()
        for c in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.CERTIFICACION,
                    id=str(c.id),
                    codigo=c.codigo,
                    titulo=f"Certificación nº {c.numero}",
                    subtitulo=c.fecha.isoformat(),
                    estado=c.estado.value,
                )
            )

    factura_ids = ids_por_entidad.get(EntidadContacto.FACTURA)
    if factura_ids:
        filas = (await session.execute(select(Factura).where(Factura.id.in_(factura_ids)))).scalars()
        for f in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.FACTURA,
                    id=str(f.id),
                    codigo=f.codigo,
                    titulo=f.concepto,
                    estado=f.estado.value,
                )
            )

    pedido_ids = ids_por_entidad.get(EntidadContacto.PEDIDO)
    if pedido_ids:
        filas = (await session.execute(select(Pedido).where(Pedido.id.in_(pedido_ids)))).scalars()
        for pe in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.PEDIDO,
                    id=str(pe.id),
                    codigo=pe.codigo,
                    titulo=pe.codigo,
                    estado=pe.estado.value,
                )
            )

    contrato_ids = ids_por_entidad.get(EntidadContacto.CONTRATO)
    if contrato_ids:
        filas = (await session.execute(select(Contrato).where(Contrato.id.in_(contrato_ids)))).scalars()
        for c in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.CONTRATO,
                    id=str(c.id),
                    codigo=c.codigo,
                    titulo=c.codigo,
                    estado=c.estado.value,
                )
            )

    albaran_ids = ids_por_entidad.get(EntidadContacto.ALBARAN)
    if albaran_ids:
        filas = (await session.execute(select(Albaran).where(Albaran.id.in_(albaran_ids)))).scalars()
        for a in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.ALBARAN,
                    id=str(a.id),
                    codigo=a.codigo,
                    titulo=a.numero_proveedor or a.codigo,
                    estado=a.estado.value,
                )
            )

    factura_recibida_ids = ids_por_entidad.get(EntidadContacto.FACTURA_RECIBIDA)
    if factura_recibida_ids:
        filas = (
            await session.execute(
                select(FacturaRecibida).where(FacturaRecibida.id.in_(factura_recibida_ids))
            )
        ).scalars()
        for fr in filas:
            resultado.append(
                AparicionOut(
                    tipo=TipoAparicion.FACTURA_RECIBIDA,
                    id=str(fr.id),
                    codigo=fr.codigo,
                    titulo=fr.numero_proveedor,
                    estado=fr.estado.value,
                )
            )

    return resultado
