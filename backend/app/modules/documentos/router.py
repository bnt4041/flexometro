"""Gestor documental (Fase 30). Mismo criterio de exposición que `crm` —
módulo `always_active`, sin `require_module` ni `require_permiso` propios:
cualquier usuario autenticado de la organización puede subir, listar,
descargar y borrar documentos, protegido por RLS de organización."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.auth import get_principal
from app.core.database import get_session
from app.modules.documentos import service
from app.modules.documentos.models import EntidadDocumento
from app.modules.documentos.schemas import DocumentoOut

router = APIRouter(prefix="/api/documentos", tags=["documentos"], dependencies=[Depends(get_principal)])


@router.get("", response_model=list[DocumentoOut])
async def listar(
    entidad: EntidadDocumento,
    entidad_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[DocumentoOut]:
    documentos = await service.listar_documentos(session, entidad, entidad_id)
    return [DocumentoOut.model_validate(d) for d in documentos]


@router.post("", response_model=DocumentoOut, status_code=status.HTTP_201_CREATED)
async def subir(
    entidad: EntidadDocumento = Form(...),
    entidad_id: uuid.UUID = Form(...),
    fichero: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> DocumentoOut:
    contenido = await fichero.read()
    try:
        documento = await service.subir_documento(
            session,
            entidad,
            entidad_id,
            fichero.filename or "sin_nombre",
            fichero.content_type or "application/octet-stream",
            contenido,
        )
    except storage.AlmacenNoConfigurado as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El gestor documental no está configurado en este servidor",
        ) from exc
    return DocumentoOut.model_validate(documento)


@router.get("/{documento_id}/descargar")
async def descargar(
    documento_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    documento = await service.obtener_documento(session, documento_id)
    if documento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    try:
        contenido = await storage.descargar_objeto(documento.object_key)
    except storage.ObjetoNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="El fichero ya no está en el almacén"
        ) from exc
    return Response(
        content=contenido,
        media_type=documento.content_type,
        headers={"Content-Disposition": f'attachment; filename="{documento.nombre_archivo}"'},
    )


@router.delete("/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    documento_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await service.eliminar_documento(session, documento_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
