"""Conversación libre sobre uno o varios documentos arrastrados a la
pestaña Partidas de una obra — mismo mecanismo que
`app.modules.ia.documento` para presupuestos, pero sobre el árbol propio de
la obra: sin banco de precios ni descompuesto (fuera de alcance a
propósito, ver el plan de "la obra como centro de la ejecución"), así que
solo puede proponer un capítulo con partidas alzadas (precio tal cual trae
el documento) o mediciones para una partida ya existente.

`obras` depende de `ia` (no al revés — `ia` no puede depender de `obras` sin
cerrar un ciclo), así que la orquestación específica de la obra vive aquí y
reutiliza de `ia` solo las piezas genéricas: la llamada a Gemini y el
registro de uso para facturación."""

import uuid

from app.core.auth import Principal
from app.core.tenancy import require_organization_id
from app.modules.core import billing_service
from app.modules.ia import gemini
from app.modules.ia.documento import validar_documentos
from app.modules.ia.schemas import MensajeConversacionIn, PropuestaAccionOut
from app.modules.obras import arbol_service
from sqlalchemy.ext.asyncio import AsyncSession


async def conversar(
    session: AsyncSession,
    documentos: list[tuple[bytes, str]],
    mensajes: list[MensajeConversacionIn],
    principal: Principal,
    *,
    obra_id: uuid.UUID,
    partida_id: uuid.UUID | None = None,
) -> tuple[str, PropuestaAccionOut | None]:
    validar_documentos(documentos)
    org_id = require_organization_id()

    partida_destino = None
    if partida_id is not None:
        partida = await arbol_service.obtener_partida(session, partida_id)
        if partida is not None and partida.obra_id == obra_id:
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
        contexto="obra",
        permitir_propuesta=True,
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
