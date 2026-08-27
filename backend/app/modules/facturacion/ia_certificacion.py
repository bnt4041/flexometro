"""Conversación libre sobre uno o varios documentos arrastrados a
`NuevaCertificacionModal` — mismo mecanismo que `app.modules.ia.documento`,
pero para preparar una certificación: no hay capítulos ni partidas que
crear, solo un formulario con una fila por partida ya presupuestada donde
hay que indicar cuánto lleva ejecutado en total. La IA solo puede proponer
rellenar esas cifras (`medicion_actual` por partida) — nunca escribe nada,
el usuario sigue creando la certificación por el camino normal.

Aparte de `router.py` porque pide además el módulo `ia` activo, igual que
`obras/ia_router.py` — mismo motivo: poder leerlas y desactivarlas juntas."""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.core.tenancy import require_organization_id
from app.modules.core import billing_service
from app.modules.ia import gemini
from app.modules.ia.documento import DocumentoInvalido, leer_documento_upload, validar_documentos
from app.modules.ia.gemini import GeminiError
from app.modules.ia.schemas import MensajeConversacionIn, RespuestaDocumento


async def conversar(
    session: AsyncSession,
    documentos: list[tuple[bytes, str]],
    mensajes: list[MensajeConversacionIn],
    principal: Principal,
    *,
    obra_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
) -> tuple[str, "gemini.PropuestaAccionOut | None"]:
    from app.modules.facturacion.service import _medicion_anterior
    from app.modules.presupuestos.models_presupuesto import Partida

    validar_documentos(documentos)
    org_id = require_organization_id()

    partidas = (
        await session.execute(
            select(Partida).where(
                Partida.presupuesto_id == presupuesto_id, Partida.organization_id == org_id
            )
        )
    ).scalars().all()
    partidas_destino = [
        {
            "id": str(p.id),
            "codigo": p.codigo,
            "resumen": p.resumen,
            "unidad": p.unidad,
            "presupuestado": str(p.medicion),
            "ya_certificado": str(await _medicion_anterior(session, obra_id, p.id)),
        }
        for p in partidas
    ]

    historial = [
        {"role": "user" if m.rol == "user" else "model", "text": m.contenido} for m in mensajes
    ]
    respuesta, propuesta, uso = await gemini.chat_documento(
        session,
        documentos,
        historial,
        contexto="certificacion",
        permitir_propuesta=True,
        partidas_certificacion=partidas_destino,
    )

    await billing_service.registrar_uso_ia(
        session,
        organization_id=org_id,
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
        proveedor="gemini",
        modelo=uso.modelo,
        tokens_entrada=uso.tokens_entrada,
        tokens_salida=uso.tokens_salida,
        referencia=None,
    )
    return respuesta, propuesta


guard = [Depends(require_module("facturacion")), Depends(require_module("ia"))]
ia_certificacion_router = APIRouter(prefix="/api/obras", tags=["facturacion"], dependencies=guard)


@ia_certificacion_router.post(
    "/{obra_id}/ia/certificacion/conversar", response_model=RespuestaDocumento
)
async def documento_conversar(
    obra_id: uuid.UUID,
    presupuesto_id: uuid.UUID = Form(...),
    # Opcional a propósito: aquí el documento no es obligatorio, la
    # conversación puede ser solo texto — ver `validar_documentos`.
    ficheros: list[UploadFile] = File(default_factory=list),
    mensajes: str = Form(...),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("facturacion", "editar")),
) -> RespuestaDocumento:
    try:
        lista = json.loads(mensajes)
        historial = [MensajeConversacionIn.model_validate(m) for m in lista]
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'mensajes' no es una lista de mensajes válida: {exc}",
        ) from exc

    documentos = [await leer_documento_upload(f) for f in ficheros]
    try:
        respuesta, propuesta = await conversar(
            session,
            documentos,
            historial,
            principal,
            obra_id=obra_id,
            presupuesto_id=presupuesto_id,
        )
    except DocumentoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except GeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    # Nada que escribir de por sí (la propuesta solo rellena un formulario
    # todavía sin guardar), pero sí queda el registro de uso para
    # facturación — se confirma para que no se pierda.
    await session.commit()
    return RespuestaDocumento(respuesta=respuesta, propuesta=propuesta)
