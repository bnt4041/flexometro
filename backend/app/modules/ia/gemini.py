"""Cliente de Gemini para leer un plano acotado (imagen o PDF) y proponer
líneas de medición.

Gemini es el proveedor de IA de este stack específicamente para visión —
DeepSeek (`deepseek.py`) cubre lo que es texto/estructura sobre datos ya
propios; esto es la excepción real: el fichero del plano sale entero hacia un
proveedor externo, porque leerlo es justo la tarea. Por eso este endpoint es
opt-in explícito y no se dispara solo.

El parseo de la respuesta está separado de la llamada de red por el mismo
motivo que en `deepseek.py`: es la parte testeable sin red ni clave, y la que
hay que blindar porque un LLM no siempre devuelve exactamente el JSON pedido.
"""

import base64
import json
import logging
from dataclasses import dataclass

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ia.credenciales import credenciales_gemini
from app.modules.ia.schemas import RespuestaLecturaPlanoLLM

logger = logging.getLogger(__name__)


class GeminiError(Exception):
    pass


@dataclass(frozen=True)
class UsoTokens:
    modelo: str
    tokens_entrada: int
    tokens_salida: int


_PROMPT = (
    "Eres un asistente de mediciones de construcción en España. Analiza este "
    "plano acotado (planta, alzado o sección) y extrae las medidas relevantes "
    "para la partida indicada. Para cada elemento que puedas medir (un muro, "
    "una estancia, un hueco...) propone una línea con el mismo modelo que usa "
    "el estado de mediciones español: 'comentario' (qué es, p. ej. el nombre "
    "de la estancia) y las dimensiones que apliquen de 'uds' (unidades, para "
    "un recuento), 'longitud', 'anchura' y 'altura' (en metros). No inventes "
    "cotas que no estén en el plano: si una medida no es legible o no aplica a "
    "este elemento, omite ese campo en vez de rellenarlo. Si algo del plano no "
    "lo puedes interpretar con confianza, dilo en 'observaciones' en vez de "
    "adivinar. Responde exclusivamente con un JSON con este esquema exacto, "
    'sin texto adicional: {"lineas": [{"comentario": string o null, "uds": '
    'number o null, "longitud": number o null, "anchura": number o null, '
    '"altura": number o null}], "observaciones": string o null}'
)


def _parsear_respuesta(contenido: str) -> RespuestaLecturaPlanoLLM:
    try:
        bruto = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini no devolvió un JSON válido: {exc}") from exc
    try:
        return RespuestaLecturaPlanoLLM.model_validate(bruto)
    except ValidationError as exc:
        raise GeminiError(
            f"La respuesta de Gemini no encaja en el esquema esperado: {exc}"
        ) from exc


async def leer_plano(
    session: AsyncSession, contenido: bytes, mime_type: str, partida_resumen: str, partida_unidad: str
) -> tuple[RespuestaLecturaPlanoLLM, UsoTokens]:
    credenciales = await credenciales_gemini(session)
    if not credenciales.api_key:
        raise GeminiError(
            "Gemini no tiene clave configurada; añádela en Administración → "
            "Ajustes IA (o GEMINI_API_KEY en el .env) para activar la lectura "
            "de planos"
        )

    contexto = (
        f"{_PROMPT}\n\nPartida a medir: «{partida_resumen}» (unidad: {partida_unidad})."
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": contexto},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(contenido).decode(),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as cliente:
            respuesta = await cliente.post(
                f"{credenciales.base_url.rstrip('/')}/models/{credenciales.modelo}:generateContent",
                json=payload,
                headers={"X-goog-api-key": credenciales.api_key},
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fallo al llamar a Gemini: %s", exc)
        raise GeminiError(f"No se pudo contactar con Gemini: {exc}") from exc

    cuerpo = respuesta.json()
    try:
        texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GeminiError(
            f"Respuesta de Gemini sin contenido interpretable: {cuerpo}"
        ) from exc

    uso_bruto = cuerpo.get("usageMetadata", {})
    tokens = UsoTokens(
        modelo=credenciales.modelo,
        tokens_entrada=int(uso_bruto.get("promptTokenCount", 0)),
        tokens_salida=int(uso_bruto.get("candidatesTokenCount", 0)),
    )
    return _parsear_respuesta(texto), tokens
