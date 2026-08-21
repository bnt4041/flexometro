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
import io
import json
import logging
from dataclasses import dataclass

import httpx
import openpyxl
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ia.credenciales import credenciales_gemini
from app.modules.ia.schemas import PropuestaAccionOut, RespuestaLecturaPlanoLLM

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


# Mimetypes de hoja de cálculo: Gemini no los entiende como `inline_data`
# (no son ni imagen ni PDF), así que se convierten a una tabla de texto plano
# antes de mandarlos — ver `_tabla_de_excel`.
MIME_EXCEL = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel.sheet.macroEnabled.12",  # .xlsm
}
MAX_FILAS_EXCEL = 500


def tabla_de_excel(contenido: bytes) -> str:
    """Cada hoja como texto delimitado por '|' — Gemini lee esto perfectamente
    bien como texto, y evita depender de que sepa parsear el binario del
    fichero (no lo sabe: sólo imagen/PDF llegan como `inline_data`)."""
    libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    partes: list[str] = []
    filas_vistas = 0
    for hoja in libro.worksheets:
        partes.append(f"### Hoja: {hoja.title}")
        for fila in hoja.iter_rows(values_only=True):
            valores = ["" if v is None else str(v) for v in fila]
            if not any(v.strip() for v in valores):
                continue
            partes.append(" | ".join(valores))
            filas_vistas += 1
            if filas_vistas >= MAX_FILAS_EXCEL:
                partes.append(f"(cortado a las {MAX_FILAS_EXCEL} filas con contenido)")
                return "\n".join(partes)
    return "\n".join(partes)


def _prompt_documento(permite_importar: bool) -> str:
    base = (
        "Eres un asistente de gestión documental de una constructora en España. "
        "Te mandan uno o varios documentos (imagen, PDF o la tabla de texto de "
        "un Excel) sin más contexto que esta conversación — puede que se vayan "
        "añadiendo más documentos a lo largo de la charla, no solo al "
        "principio. En tu PRIMERA respuesta, identifica brevemente qué tipo de "
        "documento(s) es cada uno (por ejemplo: plano acotado, presupuesto de "
        "proveedor, factura, albarán, ficha técnica, foto de obra, contrato, u "
        "otro) y qué contiene cada uno, en dos o tres frases, y termina "
        "preguntando qué quiere que hagas con ellos (leer una medida concreta, "
        "resumir un importe, comparar algo con el propio presupuesto, "
        "comparar los documentos entre sí...). A partir de ahí, responde a lo "
        "que se te pida sobre ellos: qué dicen, qué datos traen, resúmenes, lo "
        "que haga falta. Responde en español, breve y directo."
    )
    if not permite_importar:
        return (
            base
            + " Nunca digas que has guardado, aplicado o creado nada en el "
            "sistema — tú solo lees y explicas el documento; cualquier acción "
            "sobre él la hace el propio usuario desde la pantalla (por "
            "ejemplo, guardarlo), no tú."
        )
    return (
        base
        + " Si el documento trae una relación de partidas/conceptos con "
        "precio (un presupuesto de proveedor, una oferta, un albarán con "
        "precios...) y el usuario pide colgarlo del presupuesto, añadirlo, "
        "importarlo o meterlo en un capítulo aparte, usa la herramienta "
        "`proponer_importar_capitulo` con cada línea que puedas leer con "
        "claridad — resumen, unidad y precio tal cual figuran en el "
        "documento, sin inventar ni redondear lo que no se lea bien (omite "
        "esa línea si el precio o la unidad no son legibles). No es una "
        "acción real todavía: solo propones, el usuario confirma después en "
        "la pantalla. Nunca digas que ya lo has creado o guardado — la "
        "herramienta solo prepara la propuesta."
    )


_HERRAMIENTA_IMPORTAR_CAPITULO = [
    {
        "functionDeclarations": [
            {
                "name": "proponer_importar_capitulo",
                "description": (
                    "Propón crear un capítulo nuevo en el presupuesto actual con las "
                    "partidas leídas del documento. No crea nada todavía: solo deja "
                    "lista la propuesta para que el usuario la confirme."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "capitulo_resumen": {
                            "type": "STRING",
                            "description": "Nombre del capítulo nuevo",
                        },
                        "partidas": {
                            "type": "ARRAY",
                            "description": "Partidas leídas del documento, en el orden en que aparecen",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "resumen": {"type": "STRING"},
                                    "unidad": {
                                        "type": "STRING",
                                        "description": "Unidad de medida (ud, m2, m, h...)",
                                    },
                                    "precio": {
                                        "type": "NUMBER",
                                        "description": "Precio unitario tal cual figura en el documento",
                                    },
                                    "medicion": {
                                        "type": "NUMBER",
                                        "description": "Cantidad/medición, si el documento la trae (por defecto 1)",
                                    },
                                },
                                "required": ["resumen", "unidad", "precio"],
                            },
                        },
                        "descripcion": {
                            "type": "STRING",
                            "description": "Frase corta resumiendo el capítulo y cuántas partidas trae",
                        },
                    },
                    "required": ["capitulo_resumen", "partidas", "descripcion"],
                },
            }
        ]
    }
]


async def chat_documento(
    session: AsyncSession,
    documentos: list[tuple[bytes, str]],
    mensajes: list[dict],
    *,
    permitir_propuesta: bool = False,
) -> tuple[str, PropuestaAccionOut | None, UsoTokens]:
    """Conversación de varios turnos sobre uno o varios documentos (Fase
    "Arrastrar al presupuesto"). A diferencia de `leer_plano` (un turno, JSON
    forzado con un esquema fijo), aquí la salida es texto libre y hay hasta N
    turnos — mismo motivo que `deepseek.chat_con_herramientas` para "Ayuda
    con IA".

    Sin estado en el servidor: `mensajes` es el historial completo cada vez
    (`[{"role": "user"|"model", "text": str}]`) y `documentos` es la lista
    completa de ficheros conocidos hasta ahora — el cliente la reenvía
    entera en cada turno (incluidos los añadidos a media conversación), y
    aquí siempre se cuelgan del primer turno de `contents`: como se
    reconstruye toda la conversación desde cero en cada llamada, no importa
    en qué punto los añadió el usuario, solo que Gemini los vea en el
    contexto que se le manda ahora.

    `permitir_propuesta` activa la herramienta `proponer_importar_capitulo`
    (Fase 39) — solo tiene sentido cuando la conversación se abrió sobre un
    presupuesto concreto al que colgarle lo que proponga."""
    credenciales = await credenciales_gemini(session)
    if not credenciales.api_key:
        raise GeminiError(
            "Gemini no tiene clave configurada; añádela en Administración → "
            "Ajustes IA (o GEMINI_API_KEY en el .env) para activar la ayuda "
            "con documentos"
        )

    texto_excel_adjunto = ""
    partes_adjuntas: list[dict] = []
    for contenido, mime_type in documentos:
        if mime_type in MIME_EXCEL:
            texto_excel_adjunto += (
                f"\n\n--- Contenido de un Excel adjunto ---\n{tabla_de_excel(contenido)}"
            )
        else:
            partes_adjuntas.append(
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(contenido).decode(),
                    }
                }
            )

    contents = []
    for i, mensaje in enumerate(mensajes):
        texto = mensaje["text"]
        if i == 0 and texto_excel_adjunto:
            texto = f"{texto}{texto_excel_adjunto}"
        parts: list[dict] = [{"text": texto}]
        if i == 0:
            parts.extend(partes_adjuntas)
        contents.append({"role": mensaje["role"], "parts": parts})

    payload: dict = {
        "systemInstruction": {"parts": [{"text": _prompt_documento(permitir_propuesta)}]},
        "contents": contents,
    }
    if permitir_propuesta:
        payload["tools"] = _HERRAMIENTA_IMPORTAR_CAPITULO

    async def _llamar(cuerpo: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=90.0) as cliente:
                respuesta = await cliente.post(
                    f"{credenciales.base_url.rstrip('/')}/models/{credenciales.modelo}:generateContent",
                    json=cuerpo,
                    headers={"X-goog-api-key": credenciales.api_key},
                )
                respuesta.raise_for_status()
                return respuesta.json()
        except httpx.HTTPError as exc:
            logger.warning("Fallo al llamar a Gemini: %s", exc)
            raise GeminiError(f"No se pudo contactar con Gemini: {exc}") from exc

    cuerpo = await _llamar(payload)
    try:
        parte = cuerpo["candidates"][0]["content"]["parts"][0]
    except (KeyError, IndexError) as exc:
        raise GeminiError(
            f"Respuesta de Gemini sin contenido interpretable: {cuerpo}"
        ) from exc

    uso_bruto = cuerpo.get("usageMetadata", {})
    tokens_entrada = int(uso_bruto.get("promptTokenCount", 0))
    tokens_salida = int(uso_bruto.get("candidatesTokenCount", 0))

    llamada = parte.get("functionCall")
    propuesta: PropuestaAccionOut | None = None
    if llamada and llamada.get("name") == "proponer_importar_capitulo":
        try:
            argumentos = llamada.get("args") or {}
            propuesta = PropuestaAccionOut(
                tipo="importar_capitulo",
                descripcion=argumentos.get("descripcion")
                or f"Importar «{argumentos.get('capitulo_resumen', '')}»",
                capitulo_resumen=argumentos["capitulo_resumen"],
                partidas_propuestas=argumentos["partidas"],
            )
        except (KeyError, ValidationError) as exc:
            logger.warning("Propuesta de Gemini con forma inesperada: %s (%s)", argumentos, exc)
            propuesta = None

        # Un segundo turno, sin herramientas, para que redacte la frase que
        # acompaña a la propuesta — Gemini exige que se le devuelva el
        # `functionCall` (con su `thoughtSignature`) tal cual antes de seguir
        # la conversación, igual que cualquier otro proveedor con
        # function-calling: https://ai.google.dev/gemini-api/docs/thought-signatures
        contents.append({"role": "model", "parts": [parte]})
        contents.append(
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": "proponer_importar_capitulo",
                            "response": {"ok": propuesta is not None},
                        }
                    }
                ],
            }
        )
        cuerpo2 = await _llamar({**payload, "contents": contents, "tools": []})
        uso_bruto2 = cuerpo2.get("usageMetadata", {})
        tokens_entrada += int(uso_bruto2.get("promptTokenCount", 0))
        tokens_salida += int(uso_bruto2.get("candidatesTokenCount", 0))
        try:
            texto = cuerpo2["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            texto = (propuesta.descripcion if propuesta else "No he podido preparar la propuesta.")
    else:
        texto = parte.get("text", "")

    tokens = UsoTokens(
        modelo=credenciales.modelo, tokens_entrada=tokens_entrada, tokens_salida=tokens_salida
    )
    return texto.strip(), propuesta, tokens
