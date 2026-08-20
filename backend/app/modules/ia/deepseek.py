"""Cliente de DeepSeek para sugerir la estructura de un presupuesto nuevo.

Solo viaja al modelo vocabulario estructural: tipo de obra, descripción libre,
y resúmenes/unidades/códigos de capítulos y partidas frecuentes en el
histórico propio. Nunca precios, importes ni datos de cliente — el cuadro de
precios de la organización es información competitiva y no tiene por qué
salir de su servidor; a la IA solo se le pide "qué suele ir junto en este
tipo de obra", no "cuánto cuesta".

El parseo de la respuesta (`_parsear_respuesta`) está separado de la llamada
de red a propósito: es la parte que se puede testear sin API key ni
conexión, y la que hay que blindar porque un LLM no siempre devuelve el JSON
exacto que se le pide.
"""

import json
import logging
from dataclasses import dataclass

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ia.credenciales import credenciales_deepseek
from app.modules.ia.estadisticas import Estadisticas
from app.modules.ia.schemas import RespuestaLLM

logger = logging.getLogger(__name__)


class DeepSeekError(Exception):
    pass


@dataclass(frozen=True)
class UsoTokens:
    modelo: str
    tokens_entrada: int
    tokens_salida: int


_PROMPT_SISTEMA = (
    "Eres un asistente de presupuestación de construcción en España. A partir "
    "del histórico propio de una organización, propones la estructura "
    "(capítulos y las partidas de cada uno) de un presupuesto nuevo para un "
    "tipo de obra dado. Prioriza reutilizar partidas ya existentes del "
    "histórico indicando su 'codigo_existente'; solo propón partidas nuevas "
    "(es_nueva=true, codigo_existente=null) cuando falte algo típico de ese "
    "tipo de obra que no aparezca en el histórico. No incluyas precios: no "
    "los conoces y no se te piden. Responde exclusivamente con un JSON con "
    'este esquema exacto, sin texto adicional: {"capitulos": [{"resumen": '
    'string, "partidas": [{"codigo_existente": string o null, "resumen": '
    'string, "unidad": string, "es_nueva": boolean}]}]}'
)


def _prompt_usuario(tipo_obra: str, descripcion: str | None, stats: Estadisticas) -> str:
    contexto = {
        "tipo_obra": tipo_obra,
        "descripcion": descripcion,
        "historico_generico": stats.generico,
        "presupuestos_analizados": stats.total_presupuestos,
        "capitulos_frecuentes": [
            {"resumen": c.resumen, "veces": c.veces} for c in stats.capitulos
        ],
        "partidas_frecuentes": [
            {"codigo": p.codigo, "resumen": p.resumen, "unidad": p.unidad, "veces": p.veces}
            for p in stats.partidas
        ],
    }
    return (
        "Genera la estructura de presupuesto para este caso, a partir de este "
        f"histórico propio (sin precios):\n{json.dumps(contexto, ensure_ascii=False)}"
    )


def _parsear_respuesta(contenido: str) -> RespuestaLLM:
    try:
        bruto = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise DeepSeekError(f"DeepSeek no devolvió un JSON válido: {exc}") from exc
    try:
        return RespuestaLLM.model_validate(bruto)
    except ValidationError as exc:
        raise DeepSeekError(
            f"La respuesta de DeepSeek no encaja en el esquema esperado: {exc}"
        ) from exc


async def solicitar_sugerencia(
    session: AsyncSession, tipo_obra: str, descripcion: str | None, stats: Estadisticas
) -> tuple[RespuestaLLM, UsoTokens]:
    credenciales = await credenciales_deepseek(session)
    if not credenciales.api_key:
        raise DeepSeekError(
            "DeepSeek no tiene clave configurada; añádela en Administración → "
            "Ajustes IA (o DEEPSEEK_API_KEY en el .env) para activar la "
            "sugerencia de patrones"
        )

    payload = {
        "model": credenciales.modelo,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _PROMPT_SISTEMA},
            {"role": "user", "content": _prompt_usuario(tipo_obra, descripcion, stats)},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as cliente:
            respuesta = await cliente.post(
                f"{credenciales.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {credenciales.api_key}"},
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fallo al llamar a DeepSeek: %s", exc)
        raise DeepSeekError(f"No se pudo contactar con DeepSeek: {exc}") from exc

    cuerpo = respuesta.json()
    contenido = cuerpo["choices"][0]["message"]["content"]
    uso = cuerpo.get("usage", {})
    tokens = UsoTokens(
        modelo=credenciales.modelo,
        tokens_entrada=int(uso.get("prompt_tokens", 0)),
        tokens_salida=int(uso.get("completion_tokens", 0)),
    )
    return _parsear_respuesta(contenido), tokens


async def chat_con_herramientas(
    session: AsyncSession,
    mensajes: list[dict],
    herramientas: list[dict],
) -> tuple[str | None, list[dict], UsoTokens]:
    """Un turno de chat con function-calling (formato OpenAI, que DeepSeek
    implementa igual) — usado por el asistente conversacional de `asistente.py`.

    Sin JSON forzado ni esquema de respuesta: aquí lo estructurado son las
    llamadas a herramientas (`tool_calls`), que decide el propio modelo, no
    un `response_format`. Devuelve `(texto, tool_calls, uso)` — `texto` puede
    ser `None` cuando la respuesta es solo llamadas a herramientas."""
    credenciales = await credenciales_deepseek(session)
    if not credenciales.api_key:
        raise DeepSeekError(
            "DeepSeek no tiene clave configurada; añádela en Administración → "
            "Ajustes IA (o DEEPSEEK_API_KEY en el .env) para activar la ayuda con IA"
        )

    payload: dict = {
        "model": credenciales.modelo,
        "temperature": 0.3,
        "messages": mensajes,
    }
    if herramientas:
        payload["tools"] = herramientas
        payload["tool_choice"] = "auto"

    try:
        async with httpx.AsyncClient(timeout=60.0) as cliente:
            respuesta = await cliente.post(
                f"{credenciales.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {credenciales.api_key}"},
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fallo al llamar a DeepSeek: %s", exc)
        raise DeepSeekError(f"No se pudo contactar con DeepSeek: {exc}") from exc

    cuerpo = respuesta.json()
    mensaje = cuerpo["choices"][0]["message"]
    uso = cuerpo.get("usage", {})
    tokens = UsoTokens(
        modelo=credenciales.modelo,
        tokens_entrada=int(uso.get("prompt_tokens", 0)),
        tokens_salida=int(uso.get("completion_tokens", 0)),
    )
    contenido = mensaje.get("content")
    return (contenido.strip() if contenido else None), mensaje.get("tool_calls") or [], tokens
