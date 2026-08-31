"""El catálogo inicial de avisos.

Van juntos aquí y no repartidos por cada módulo por una razón práctica: los
buscadores de las vigilancias necesitan los modelos de esos módulos, y
declararlos desde dentro cerraría ciclos de importación con `notificaciones`.
Los imports viven dentro de cada función, no arriba, por lo mismo.

Nada impide que un módulo registre lo suyo con `catalogo.registrar()`: esto
es el punto de partida, no la lista cerrada.

Un buscador devuelve `(clave, titulo, cuerpo, enlace)` por cada candidato.
`clave` identifica el registro y es lo que evita repetir el mismo aviso día
tras día (ver `AvisoEmitido`).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.eventos import (
    Disparador,
    Parametro,
    TipoEvento,
    registrar,
)


async def _obras_estancadas(
    session: AsyncSession, organization_id, parametros: dict
) -> list[tuple[str, str, str, str]]:
    from app.modules.obras.models import EstadoObra, Obra

    dias = int(parametros.get("dias", 90))
    corte = datetime.now(UTC) - timedelta(days=dias)
    filas = await session.scalars(
        select(Obra).where(
            Obra.organization_id == organization_id,
            Obra.estado_desde < corte,
            # Una obra finalizada o cerrada no está estancada: está acabada.
            Obra.estado.notin_([EstadoObra.FINALIZADA, EstadoObra.CERRADA]),
        )
    )
    salida = []
    for obra in filas:
        parada = (datetime.now(UTC) - obra.estado_desde).days
        salida.append(
            (
                str(obra.id),
                f"Obra parada: {obra.nombre}",
                f"Lleva {parada} días en «{obra.estado.value}» sin cambiar de estado.",
                f"/obras/{obra.id}",
            )
        )
    return salida


async def _documentos_prl_por_caducar(
    session: AsyncSession, organization_id, parametros: dict
) -> list[tuple[str, str, str, str]]:
    from app.modules.prl.models import DocumentoPRL, TipoDocumentoPRL

    dias = int(parametros.get("dias", 30))
    limite = date.today() + timedelta(days=dias)
    filas = await session.execute(
        select(DocumentoPRL, TipoDocumentoPRL.nombre)
        .join(TipoDocumentoPRL, TipoDocumentoPRL.id == DocumentoPRL.tipo_id)
        .where(
            DocumentoPRL.organization_id == organization_id,
            DocumentoPRL.fecha_caducidad <= limite,
        )
    )
    salida = []
    for documento, nombre_tipo in filas.all():
        restan = (documento.fecha_caducidad - date.today()).days
        cuerpo = (
            f"Caducó hace {abs(restan)} días."
            if restan < 0
            else f"Caduca en {restan} días ({documento.fecha_caducidad:%d/%m/%Y})."
        )
        salida.append(
            (
                # La fecha entra en la clave: si se renueva el documento y se
                # le pone otra caducidad, vuelve a poder avisar. Con solo el
                # id, un documento avisado una vez no volvería a avisar nunca.
                f"{documento.id}:{documento.fecha_caducidad.isoformat()}",
                f"{nombre_tipo}: {'caducado' if restan < 0 else 'caduca pronto'}",
                cuerpo,
                "/prl",
            )
        )
    return salida


async def _facturas_vencidas(
    session: AsyncSession, organization_id, parametros: dict
) -> list[tuple[str, str, str, str]]:
    from app.modules.facturacion.models import EstadoFactura, Factura

    dias = int(parametros.get("dias", 1))
    corte = date.today() - timedelta(days=dias)
    filas = await session.scalars(
        select(Factura).where(
            Factura.organization_id == organization_id,
            Factura.fecha_vencimiento.is_not(None),
            Factura.fecha_vencimiento < corte,
            # Solo emitidas: un borrador no vence y una anulada ya no existe.
            # NO se filtra por cobrada porque la aplicación todavía no lleva
            # los cobros — quien reciba el aviso tendrá que comprobarlo.
            Factura.estado == EstadoFactura.EMITIDA,
        )
    )
    salida = []
    for factura in filas:
        vencida = (date.today() - factura.fecha_vencimiento).days
        salida.append(
            (
                str(factura.id),
                f"Factura vencida: {factura.serie}-{factura.numero}",
                f"Venció hace {vencida} días.",
                f"/facturas/{factura.id}",
            )
        )
    return salida


def registrar_catalogo_inicial() -> None:
    """Idempotente: se puede llamar más de una vez sin reventar (los tests
    reimportan módulos con más alegría que la aplicación)."""
    from app.core.eventos import obtener

    if obtener("obra.estancada") is not None:
        return

    registrar(
        TipoEvento(
            codigo="obra.estancada",
            modulo="obras",
            etiqueta="Obra sin movimiento",
            descripcion=(
                "Una obra que lleva demasiado tiempo en el mismo estado. No "
                "cuenta cualquier edición: solo el cambio de estado."
            ),
            disparador=Disparador.VIGILANCIA,
            parametros=(
                Parametro(nombre="dias", etiqueta="Días sin cambiar de estado", por_defecto=90),
            ),
        ),
        _obras_estancadas,
    )
    registrar(
        TipoEvento(
            codigo="prl.documento_caduca",
            modulo="prl",
            etiqueta="Documento PRL a punto de caducar",
            descripcion=(
                "Documentos de PRL —empresa, personal, recursos u obra— que "
                "caducan pronto o ya caducaron."
            ),
            disparador=Disparador.VIGILANCIA,
            parametros=(
                Parametro(nombre="dias", etiqueta="Avisar con antelación de", por_defecto=30),
            ),
        ),
        _documentos_prl_por_caducar,
    )
    registrar(
        TipoEvento(
            codigo="facturacion.factura_vencida",
            modulo="facturacion",
            etiqueta="Factura vencida",
            descripcion=(
                "Facturas emitidas cuyo vencimiento ya ha pasado. Ojo: la "
                "aplicación todavía no lleva los cobros, así que avisa "
                "también de las que ya estén pagadas."
            ),
            disparador=Disparador.VIGILANCIA,
            parametros=(
                Parametro(nombre="dias", etiqueta="Días desde el vencimiento", por_defecto=1),
            ),
        ),
        _facturas_vencidas,
    )

    # ── Hechos: los emite el código en el momento ───────────────────────
    for codigo, modulo, etiqueta, descripcion in (
        ("firma.completada", "prl", "Documento firmado por todas las partes",
         "Cuando el último firmante firma y el documento queda cerrado."),
        ("firma.rechazada", "prl", "Firma rechazada",
         "Cuando alguien se niega a firmar. Tumba el documento entero."),
        ("compras.oferta_recibida", "compras", "Oferta de proveedor recibida",
         "Cuando un proveedor contesta a una solicitud de precios."),
    ):
        registrar(
            TipoEvento(
                codigo=codigo, modulo=modulo, etiqueta=etiqueta,
                descripcion=descripcion, disparador=Disparador.HECHO,
            )
        )
