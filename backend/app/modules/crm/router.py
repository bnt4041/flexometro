"""CRM (Fase 29): notas de seguimiento. Mismo criterio de exposición que
`campos_libres` — módulo `always_active`, sin `require_module` ni
`require_permiso` propios: cualquier usuario autenticado de la organización
puede leer y escribir notas, protegido solo por RLS de organización, igual
que los valores de campos libres."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.mailer import MailerError
from app.modules.crm import service
from app.modules.crm.models import EntidadNota
from app.modules.crm.schemas import EnviarEmailIn, NotaCreate, NotaOut

# 15 MB por adjunto nuevo: de sobra para una factura o un PDF de obra, sin
# arriesgarse a que un correo grande se quede a medias por el SMTP.
TAMANO_MAXIMO_ADJUNTO = 15 * 1024 * 1024

router = APIRouter(prefix="/api/notas", tags=["crm"], dependencies=[Depends(get_principal)])


@router.get("", response_model=list[NotaOut])
async def listar(
    entidad: EntidadNota,
    entidad_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[NotaOut]:
    notas = await service.listar_notas(session, entidad, entidad_id)
    return [NotaOut.model_validate(n) for n in notas]


@router.post("", response_model=NotaOut, status_code=status.HTTP_201_CREATED)
async def crear(
    entidad: EntidadNota,
    entidad_id: uuid.UUID,
    datos: NotaCreate,
    session: AsyncSession = Depends(get_session),
) -> NotaOut:
    nota = await service.crear_nota(session, entidad, entidad_id, datos)
    return NotaOut.model_validate(nota)


@router.delete("/{nota_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    nota_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await service.eliminar_nota(session, nota_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota no encontrada")


@router.post("/enviar-email", response_model=NotaOut, status_code=status.HTTP_201_CREATED)
async def enviar_email(
    entidad: EntidadNota,
    entidad_id: uuid.UUID,
    destinatario: str = Form(...),
    asunto: str = Form(...),
    cuerpo_html: str = Form(...),
    documento_ids: list[uuid.UUID] = Form(default=[]),
    guardar_adjuntos: bool = Form(default=True),
    archivos: list[UploadFile] = File(default=[]),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> NotaOut:
    """Multipart, no JSON: además de adjuntar documentos ya existentes
    (`documento_ids`), se pueden arrastrar ficheros nuevos directamente
    (`archivos`) — `guardar_adjuntos` decide si esos ficheros nuevos quedan
    también como documento de la ficha o solo viajan en el correo."""
    if principal.organization_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin organización activa")

    try:
        datos = EnviarEmailIn(
            destinatario=destinatario, asunto=asunto, cuerpo_html=cuerpo_html, documento_ids=documento_ids
        )
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    archivos_nuevos: list[tuple[str, str, bytes]] = []
    for archivo in archivos:
        contenido = await archivo.read()
        if len(contenido) > TAMANO_MAXIMO_ADJUNTO:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{archivo.filename}' supera los 15 MB",
            )
        archivos_nuevos.append(
            (archivo.filename or "sin_nombre", archivo.content_type or "application/octet-stream", contenido)
        )

    try:
        nota = await service.enviar_email(
            session,
            principal.organization_id,
            entidad,
            entidad_id,
            datos,
            archivos_nuevos=archivos_nuevos,
            guardar_adjuntos=guardar_adjuntos,
        )
    except MailerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return NotaOut.model_validate(nota)
