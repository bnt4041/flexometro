"""Rutas de "arrastrar un documento" sobre el árbol de la obra — hermanas de
las de `arbol_router.py` pero aparte, igual que esas ya están separadas de
`router.py`: piden además el módulo `ia` activo, así que conviene poder
leerlas y desactivarlas juntas."""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.modules.ia import documento as ia_documento
from app.modules.ia.documento import DocumentoInvalido
from app.modules.ia.gemini import GeminiError
from app.modules.ia.schemas import MensajeConversacionIn, RespuestaDocumento
from app.modules.obras import arbol_service, service
from app.modules.obras import ia_documento as obra_ia_documento
from app.modules.obras.schemas import (
    AplicarMedicionesIAObra,
    AplicarPropuestaIAObra,
    MedicionObraOut,
)

guard = [Depends(require_module("obras")), Depends(require_module("ia"))]
ia_router = APIRouter(prefix="/api/obras", tags=["obras"], dependencies=guard)


@ia_router.post("/{obra_id}/ia/documentos/conversar", response_model=RespuestaDocumento)
async def documento_conversar(
    obra_id: uuid.UUID,
    # Opcional a propósito: aquí el documento no es obligatorio, la
    # conversación puede ser solo texto — ver `validar_documentos`.
    ficheros: list[UploadFile] = File(default_factory=list),
    mensajes: str = Form(...),
    partida_id: uuid.UUID | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> RespuestaDocumento:
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    try:
        lista = json.loads(mensajes)
        historial = [MensajeConversacionIn.model_validate(m) for m in lista]
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'mensajes' no es una lista de mensajes válida: {exc}",
        ) from exc

    documentos = [await ia_documento.leer_documento_upload(f) for f in ficheros]
    try:
        respuesta, propuesta = await obra_ia_documento.conversar(
            session,
            documentos,
            historial,
            principal,
            obra_id=obra_id,
            partida_id=partida_id,
        )
    except DocumentoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except GeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    await session.commit()
    return RespuestaDocumento(respuesta=respuesta, propuesta=propuesta)


@ia_router.post(
    "/{obra_id}/ia/aplicar-propuesta", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def aplicar_propuesta_ia(
    obra_id: uuid.UUID,
    datos: AplicarPropuestaIAObra,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "crear")),
) -> dict:
    """Crea el capítulo + partidas alzadas que la IA propuso al leer un
    documento, en un solo paso — como `aplicar_propuesta_ia` en presupuestos,
    pero sin descompuesto: cada partida lleva su precio y medición tal cual
    los propuso la IA."""
    obra = await service.obtener_obra(session, obra_id)
    if obra is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")
    capitulo = await arbol_service.crear_capitulo(session, obra, resumen=datos.capitulo_resumen)
    for p in datos.partidas:
        partida = await arbol_service.crear_partida(
            session, capitulo, resumen=p.resumen, unidad=p.unidad, precio=p.precio
        )
        await arbol_service.crear_medicion(session, partida, uds=p.medicion)
    await session.commit()
    return {
        "id": str(capitulo.id),
        "resumen": capitulo.resumen,
        "partidas": len(datos.partidas),
    }


@ia_router.post("/ia/mediciones/aplicar-directo", response_model=list[MedicionObraOut])
async def aplicar_mediciones_ia(
    datos: AplicarMedicionesIAObra,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("obras", "editar")),
) -> list[MedicionObraOut]:
    """Confirma una propuesta `anadir_mediciones_partida` salida de la
    conversación sobre un documento — sin lectura de plano de por medio (esa
    es solo para presupuestos), la partida de destino viaja explícita."""
    partida = await arbol_service.obtener_partida(session, datos.partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    creadas = [
        await arbol_service.crear_medicion(
            session,
            partida,
            comentario=linea.comentario,
            uds=linea.uds,
            longitud=linea.longitud,
            anchura=linea.anchura,
            altura=linea.altura,
        )
        for linea in datos.lineas
    ]
    await session.commit()
    return [MedicionObraOut.model_validate(l) for l in creadas]
