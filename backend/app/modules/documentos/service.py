import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.documentos.models import Documento, EntidadDocumento

# Tabla donde vive el `codigo` legible de cada tipo de ficha — sin FK real
# (mismo criterio que el resto de `entidad`/`entidad_id` de este módulo), así
# que resolver la etiqueta es una consulta aparte por tipo, no un join.
# (tabla, columna que sirve de "código" en el buscador) — casi todas usan
# `codigo`, pero `contacto` no tiene esa columna (es una persona, no un
# documento numerado), así que se identifica por su nombre.
_TABLA_POR_ENTIDAD: dict[EntidadDocumento, tuple[str, str]] = {
    EntidadDocumento.TERCERO: ("terceros.tercero", "codigo"),
    EntidadDocumento.PRESUPUESTO: ("presupuestos.presupuesto", "codigo"),
    EntidadDocumento.OBRA: ("obras.obra", "codigo"),
    EntidadDocumento.CERTIFICACION: ("facturacion.certificacion", "codigo"),
    EntidadDocumento.FACTURA: ("facturacion.factura", "codigo"),
    EntidadDocumento.CONTACTO: ("terceros.contacto", "nombre"),
    EntidadDocumento.CONCEPTO: ("presupuestos.concepto", "codigo"),
    EntidadDocumento.SOLICITUD_PRECIOS: ("compras.solicitud_precios", "codigo"),
    EntidadDocumento.PEDIDO: ("compras.pedido", "codigo"),
    EntidadDocumento.CONTRATO: ("contratos.contrato", "codigo"),
    EntidadDocumento.ALBARAN: ("compras.albaran", "codigo"),
    EntidadDocumento.FACTURA_RECIBIDA: ("compras.factura_recibida", "codigo"),
    EntidadDocumento.PERSONAL: ("obras.personal", "codigo"),
    EntidadDocumento.RECURSO: ("prl.recurso", "codigo"),
    EntidadDocumento.SOLICITUD_FIRMA: ("prl.solicitud_firma", "codigo"),
    # `PRL_EMPRESA` no aparece a propósito: su `entidad_id` es la propia
    # organización, y `core.organization` no tiene `organization_id` con el
    # que filtrar. Se queda sin código, que es lo correcto — no cuelga de
    # ninguna ficha.
}


async def listar_documentos(
    session: AsyncSession, entidad: EntidadDocumento, entidad_id: uuid.UUID
) -> list[Documento]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(Documento)
        .where(
            Documento.organization_id == org_id,
            Documento.entidad == entidad,
            Documento.entidad_id == entidad_id,
        )
        .order_by(Documento.created_at.desc())
    )
    return list(filas.scalars())


async def obtener_documento(session: AsyncSession, documento_id: uuid.UUID) -> Documento | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Documento).where(Documento.id == documento_id, Documento.organization_id == org_id)
    )


async def subir_documento(
    session: AsyncSession,
    entidad: EntidadDocumento,
    entidad_id: uuid.UUID,
    nombre_archivo: str,
    content_type: str,
    contenido: bytes,
) -> Documento:
    org_id = require_organization_id()
    object_key = f"{org_id}/{entidad}/{entidad_id}/{uuid.uuid4()}-{nombre_archivo}"
    await storage.subir_objeto(object_key, contenido, content_type)

    documento = Documento(
        organization_id=org_id,
        entidad=entidad,
        entidad_id=entidad_id,
        nombre_archivo=nombre_archivo,
        content_type=content_type,
        tamano_bytes=len(contenido),
        object_key=object_key,
        **datos_autoria(),
    )
    session.add(documento)
    await session.flush()
    return documento


async def eliminar_documento(session: AsyncSession, documento_id: uuid.UUID) -> bool:
    documento = await obtener_documento(session, documento_id)
    if documento is None:
        return False
    await storage.eliminar_objeto(documento.object_key)
    await session.delete(documento)
    await session.flush()
    return True


async def buscar_documentos(
    session: AsyncSession, q: str, *, limite: int = 30
) -> list[tuple[Documento, str | None]]:
    """Por nombre de archivo, en toda la cuenta — para el selector de
    adjuntos del correo (Fase 42): "primero los de la ficha, si no, un
    buscador" (ver `enviar_email`). Devuelve cada documento con el código de
    su ficha de origen ya resuelto, agrupable por `entidad` en el frontend."""
    org_id = require_organization_id()
    filas = (
        await session.execute(
            select(Documento)
            .where(Documento.organization_id == org_id, Documento.nombre_archivo.ilike(f"%{q}%"))
            .order_by(Documento.created_at.desc())
            .limit(limite)
        )
    ).scalars()
    documentos = list(filas)

    ids_por_entidad: dict[EntidadDocumento, set[uuid.UUID]] = {}
    for documento in documentos:
        ids_por_entidad.setdefault(documento.entidad, set()).add(documento.entidad_id)

    codigos: dict[tuple[EntidadDocumento, uuid.UUID], str] = {}
    for entidad, ids in ids_por_entidad.items():
        # `.get()` y no `[...]`: un tipo de entidad sin tabla asociada (o uno
        # nuevo que se añada al enum y se olvide aquí) tiene que dejar el
        # documento SIN código, no tumbar la búsqueda entera. Pasó al añadir
        # el módulo PRL: un solo documento de un tipo no mapeado rompía el
        # buscador para todos los demás.
        mapeo = _TABLA_POR_ENTIDAD.get(entidad)
        if mapeo is None:
            continue
        # `tabla`/`columna` salen del diccionario fijo de arriba, nunca de
        # `q` ni de ningún dato de entrada: no hay inyección posible al
        # interpolarlos.
        tabla, columna = mapeo
        filas_codigo = await session.execute(
            text(f"SELECT id, {columna} FROM {tabla} WHERE id = ANY(:ids) AND organization_id = :org_id"),
            {"ids": list(ids), "org_id": org_id},
        )
        for entidad_id, codigo in filas_codigo:
            codigos[(entidad, entidad_id)] = codigo

    return [(d, codigos.get((d.entidad, d.entidad_id))) for d in documentos]


async def arbol_documentos(
    session: AsyncSession, *, content_type: str | None = None, limite: int = 500
) -> list[tuple[EntidadDocumento, uuid.UUID, str | None, list[Documento]]]:
    """La biblioteca agrupada por ficha de origen, para poder NAVEGARLA en vez
    de tener que acertar el nombre en el buscador.

    Devuelve `(entidad, entidad_id, código, documentos)`. La agrupación se
    hace aquí y no en el cliente porque el código de cada ficha solo se puede
    resolver con una consulta por tipo de entidad — igual que en
    `buscar_documentos`, cuya lógica de resolución se reutiliza."""
    org_id = require_organization_id()
    filtros = [Documento.organization_id == org_id]
    if content_type:
        filtros.append(Documento.content_type == content_type)
    documentos = list(
        (
            await session.execute(
                select(Documento).where(*filtros).order_by(Documento.created_at.desc()).limit(limite)
            )
        ).scalars()
    )
    if not documentos:
        return []

    ids_por_entidad: dict[EntidadDocumento, set[uuid.UUID]] = {}
    for documento in documentos:
        ids_por_entidad.setdefault(documento.entidad, set()).add(documento.entidad_id)

    codigos: dict[tuple[EntidadDocumento, uuid.UUID], str] = {}
    for entidad, ids in ids_por_entidad.items():
        mapeo = _TABLA_POR_ENTIDAD.get(entidad)
        if mapeo is None:
            continue
        tabla, columna = mapeo
        filas = await session.execute(
            text(
                f"SELECT id, {columna} FROM {tabla} WHERE id = ANY(:ids) AND organization_id = :org_id"
            ),
            {"ids": list(ids), "org_id": org_id},
        )
        for entidad_id, codigo in filas:
            codigos[(entidad, entidad_id)] = codigo

    grupos: dict[tuple[EntidadDocumento, uuid.UUID], list[Documento]] = {}
    for documento in documentos:
        grupos.setdefault((documento.entidad, documento.entidad_id), []).append(documento)

    return [
        (entidad, entidad_id, codigos.get((entidad, entidad_id)), docs)
        for (entidad, entidad_id), docs in grupos.items()
    ]
