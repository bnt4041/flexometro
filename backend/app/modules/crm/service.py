import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.crm.models import EntidadNota, Nota, TipoNota
from app.modules.crm.schemas import EnviarEmailIn, NotaCreate


async def listar_notas(session: AsyncSession, entidad: EntidadNota, entidad_id: uuid.UUID) -> list[Nota]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(Nota)
        .where(
            Nota.organization_id == org_id,
            Nota.entidad == entidad,
            Nota.entidad_id == entidad_id,
        )
        .order_by(Nota.created_at.desc())
    )
    return list(filas.scalars())


async def crear_nota(
    session: AsyncSession, entidad: EntidadNota, entidad_id: uuid.UUID, datos: NotaCreate
) -> Nota:
    org_id = require_organization_id()
    nota = Nota(
        organization_id=org_id,
        entidad=entidad,
        entidad_id=entidad_id,
        contenido=datos.contenido,
        **datos_autoria(),
    )
    session.add(nota)
    await session.flush()
    return nota


async def eliminar_nota(session: AsyncSession, nota_id: uuid.UUID) -> bool:
    org_id = require_organization_id()
    nota = await session.scalar(
        select(Nota).where(Nota.id == nota_id, Nota.organization_id == org_id)
    )
    if nota is None:
        return False
    await session.delete(nota)
    await session.flush()
    return True


async def enviar_email(
    session: AsyncSession,
    organization_id: uuid.UUID,
    entidad: EntidadNota,
    entidad_id: uuid.UUID,
    datos: EnviarEmailIn,
    *,
    archivos_nuevos: list[tuple[str, str, bytes]] | None = None,
    guardar_adjuntos: bool = True,
) -> Nota:
    """Envía el correo y, solo si el envío ha ido bien, deja constancia como
    nota — un envío fallido no debe aparecer en la bitácora como si hubiera
    llegado. Usa el SMTP propio de la organización si lo tiene configurado
    (host relleno); si no, cae al de la plataforma, para que la función
    sirva sin que cada organización tenga que configurar nada.

    `archivos_nuevos` son ficheros que no existían como documento todavía
    (arrastrados directamente al redactar el correo, Fase 42): si
    `guardar_adjuntos` es verdad se suben también como documento de la
    ficha (quedan descargables después); si no, solo viajan en el correo —
    la nota los recuerda por nombre, pero sin nada que descargar más tarde."""
    from app.core import mailer, storage
    from app.modules.core import settings_service
    from app.modules.documentos import service as documentos_service
    from app.modules.documentos.models import EntidadDocumento

    org_id = require_organization_id()

    config = await settings_service.configuracion_smtp_de(session, organization_id)

    adjuntos: list[tuple[str, str, bytes]] = []
    adjuntos_nota: list[dict] = []
    for documento_id in datos.documento_ids:
        documento = await documentos_service.obtener_documento(session, documento_id)
        if documento is None:
            continue
        contenido = await storage.descargar_objeto(documento.object_key)
        adjuntos.append((documento.nombre_archivo, documento.content_type, contenido))
        adjuntos_nota.append({"documento_id": str(documento.id), "nombre_archivo": documento.nombre_archivo})

    for nombre_archivo, content_type, contenido in archivos_nuevos or []:
        adjuntos.append((nombre_archivo, content_type, contenido))
        if guardar_adjuntos:
            documento = await documentos_service.subir_documento(
                session, EntidadDocumento(entidad.value), entidad_id, nombre_archivo, content_type, contenido
            )
            adjuntos_nota.append({"documento_id": str(documento.id), "nombre_archivo": nombre_archivo})
        else:
            adjuntos_nota.append({"documento_id": None, "nombre_archivo": nombre_archivo})

    await mailer.enviar_correo(
        config,
        destinatario=datos.destinatario,
        asunto=datos.asunto,
        cuerpo_html=datos.cuerpo_html,
        adjuntos=adjuntos,
    )

    nota = Nota(
        organization_id=org_id,
        entidad=entidad,
        entidad_id=entidad_id,
        contenido=datos.cuerpo_html,
        tipo=TipoNota.EMAIL,
        asunto=datos.asunto,
        destinatario=datos.destinatario,
        adjuntos=adjuntos_nota,
        **datos_autoria(),
    )
    session.add(nota)
    await session.flush()
    return nota
