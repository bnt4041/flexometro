"""Conversación libre sobre un documento (PDF, imagen o Excel) arrastrado al
presupuesto — Fase "Arrastrar al presupuesto". Sin estado en el servidor:
cada turno manda el documento entero más el historial de texto, igual que
`asistente.py` para "Ayuda con IA" (que es solo texto; aquí además hay un
fichero, adjunto una única vez por `gemini.chat_documento`).

Guardar el documento en el presupuesto es una acción aparte del usuario
contra el módulo de `documentos` — esta conversación no escribe nada por su
cuenta. Lo único que sí puede proponer (Fase 39, cuando se sabe sobre qué
presupuesto se abrió) es un capítulo nuevo con lo que lea del documento —
propuesta, nunca una escritura directa (ver el system prompt en `gemini.py`)."""

import uuid

from app.core.auth import Principal
from app.core.tenancy import require_organization_id
from app.modules.core import billing_service
from app.modules.ia import gemini
from app.modules.ia.schemas import MensajeConversacionIn, PropuestaAccionOut
from sqlalchemy.ext.asyncio import AsyncSession

MIME_PERMITIDOS = {"application/pdf", "image/png", "image/jpeg", "image/webp", *gemini.MIME_EXCEL}
# Mismo tope que `medicion.py`: un documento de obra cabe de sobra, y evita
# que un archivo enorme se cuele entero en cada turno de la conversación.
MAX_TAMANO_BYTES = 15 * 1024 * 1024


class DocumentoInvalido(Exception):
    pass


async def conversar(
    session: AsyncSession,
    contenido: bytes,
    mime_type: str,
    mensajes: list[MensajeConversacionIn],
    principal: Principal,
    *,
    presupuesto_id: uuid.UUID | None = None,
) -> tuple[str, PropuestaAccionOut | None]:
    if mime_type not in MIME_PERMITIDOS:
        raise DocumentoInvalido(f"Tipo de fichero no admitido: {mime_type}")
    if len(contenido) > MAX_TAMANO_BYTES:
        raise DocumentoInvalido(
            f"El fichero supera el máximo de {MAX_TAMANO_BYTES // (1024 * 1024)} MB"
        )

    org_id = require_organization_id()
    historial = [
        {"role": "user" if m.rol == "user" else "model", "text": m.contenido} for m in mensajes
    ]
    respuesta, propuesta, uso = await gemini.chat_documento(
        session,
        contenido,
        mime_type,
        historial,
        permitir_propuesta=presupuesto_id is not None,
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
