"""Conversación libre sobre uno o varios documentos (PDF, imagen o Excel)
arrastrados al presupuesto — Fase "Arrastrar al presupuesto". Sin estado en
el servidor: cada turno manda todos los documentos conocidos hasta ahora
más el historial de texto, igual que `asistente.py` para "Ayuda con IA"
(que es solo texto; aquí además hay ficheros, adjuntos por
`gemini.chat_documento`).

Los documentos se pueden ir añadiendo a media conversación (Fase 41): como
no hay estado en el servidor, el cliente simplemente reenvía la lista
completa —los de antes y los nuevos— en cada turno.

Guardar un documento en el presupuesto es una acción aparte del usuario
contra el módulo de `documentos` — esta conversación no escribe nada por su
cuenta. Lo único que sí puede proponer (Fase 39, cuando se sabe sobre qué
presupuesto se abrió) es un capítulo nuevo con lo que lea de los
documentos — propuesta, nunca una escritura directa (ver el system prompt
en `gemini.py`)."""

import uuid

from fastapi import UploadFile

from app.core.auth import Principal
from app.core.tenancy import require_organization_id
from app.modules.core import billing_service
from app.modules.ia import gemini
from app.modules.ia.schemas import MensajeConversacionIn, PropuestaAccionOut
from app.modules.presupuestos.presupuesto_service import obtener_partida
from sqlalchemy.ext.asyncio import AsyncSession

MIME_PERMITIDOS = {"application/pdf", "image/png", "image/jpeg", "image/webp", *gemini.MIME_EXCEL}
# Mismo tope que `medicion.py` para un fichero suelto; el conjunto además no
# puede pasar de MAX_TOTAL_BYTES ni de MAX_FICHEROS, para que una
# conversación con varios documentos grandes no se cuele entera en cada
# turno sin límite.
MAX_TAMANO_BYTES = 15 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_FICHEROS = 6

_EXTENSIONES_EXCEL = {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


async def leer_documento_upload(fichero: UploadFile) -> tuple[bytes, str]:
    """Bytes + tipo MIME real de un `UploadFile` — el navegador a veces no
    sabe el tipo correcto de un .xlsx y manda algo genérico; la extensión es
    la señal fiable, igual que con el BC3. Compartido entre el chat de
    documentos de presupuestos, obras y certificaciones — un único sitio
    para esta conversión en vez de repetirla en cada router."""
    contenido = await fichero.read()
    mime_type = fichero.content_type or "application/octet-stream"
    if mime_type not in MIME_PERMITIDOS:
        for extension, mime_real in _EXTENSIONES_EXCEL.items():
            if (fichero.filename or "").lower().endswith(extension):
                mime_type = mime_real
                break
    return contenido, mime_type


class DocumentoInvalido(Exception):
    pass


def validar_documentos(documentos: list[tuple[bytes, str]]) -> None:
    """Mismas comprobaciones para cualquier conversación sobre documentos
    arrastrados, sea sobre un presupuesto (`conversar`, aquí abajo), una obra
    (`app.modules.obras.ia_documento`) o una certificación
    (`app.modules.facturacion.ia_certificacion`) — un único sitio para los
    límites en vez de repetirlos en cada módulo.

    Una lista vacía es válida a propósito: el documento es opcional — la
    conversación puede ser solo texto ("certifica el 33% de todo") y el
    usuario adjunta algo más tarde, o nunca."""
    if len(documentos) > MAX_FICHEROS:
        raise DocumentoInvalido(f"No se pueden adjuntar más de {MAX_FICHEROS} ficheros a la vez")
    for _contenido, mime_type in documentos:
        if mime_type not in MIME_PERMITIDOS:
            raise DocumentoInvalido(f"Tipo de fichero no admitido: {mime_type}")
    for contenido, _mime_type in documentos:
        if len(contenido) > MAX_TAMANO_BYTES:
            raise DocumentoInvalido(
                f"Un fichero supera el máximo de {MAX_TAMANO_BYTES // (1024 * 1024)} MB"
            )
    total = sum(len(contenido) for contenido, _ in documentos)
    if total > MAX_TOTAL_BYTES:
        raise DocumentoInvalido(
            f"Entre todos los ficheros suman más de {MAX_TOTAL_BYTES // (1024 * 1024)} MB"
        )


async def conversar(
    session: AsyncSession,
    documentos: list[tuple[bytes, str]],
    mensajes: list[MensajeConversacionIn],
    principal: Principal,
    *,
    presupuesto_id: uuid.UUID | None = None,
    partida_id: uuid.UUID | None = None,
) -> tuple[str, PropuestaAccionOut | None]:
    validar_documentos(documentos)
    org_id = require_organization_id()

    partida_destino = None
    if partida_id is not None:
        # El documento se soltó sobre una partida ya existente (no la raíz
        # ni un capítulo): además de poder crear capítulos nuevos, la IA
        # puede proponer mediciones para ESTA partida en concreto — el caso
        # típico de soltar un plano acotado encima de la partida a la que
        # corresponde, en vez de dejar que cree una duplicada.
        partida = await obtener_partida(session, partida_id)
        if partida is not None:
            partida_destino = {
                "id": str(partida.id),
                "resumen": partida.resumen,
                "unidad": partida.unidad,
            }

    historial = [
        {"role": "user" if m.rol == "user" else "model", "text": m.contenido} for m in mensajes
    ]
    respuesta, propuesta, uso = await gemini.chat_documento(
        session,
        documentos,
        historial,
        permitir_propuesta=presupuesto_id is not None,
        partida_destino=partida_destino,
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
