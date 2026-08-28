"""Reconocimiento de elementos y sus dimensiones reales en una foto de obra
— ver `/testmeter`.

Dos decisiones que vienen de lo que falló en el primer intento de esto:

1. **El cuadro delimitador usa el formato documentado de Gemini**
   (`box_2d = [ymin, xmin, ymax, xmax]`, enteros normalizados a 0-1000, con
   origen arriba-izquierda), no uno inventado. Los modelos de 2.0 en adelante
   están entrenados específicamente para emitir ESE formato; pedirles otro
   (fracciones 0-1, x/y/ancho/alto) da cajas mucho peores, que era justo el
   problema de la primera versión.
   https://ai.google.dev/gemini-api/docs/image-understanding

2. **La IA da la medida real de cada elemento, no una escala px→cm global.**
   Una escala uniforme solo vale para lo que esté en el MISMO plano que la
   referencia: en una foto de una habitación, la pared del fondo y la de al
   lado tienen escalas distintas, así que una única cifra de px/cm mide mal
   todo lo que no sea coplanario. Estimar la dimensión de cada elemento por
   separado deja el problema de la perspectiva del lado del modelo, que es
   quien puede razonarlo.

Gemini es el proveedor de visión de este stack (ver `app/modules/ia/gemini.py`).
A diferencia de `leer_plano`, esto no cuelga de una sesión de base de datos ni
de una organización: la ruta pública que lo usa no tiene ninguna de las dos,
así que la clave sale directa del `.env` en vez de pasar por
`credenciales_gemini` — y por lo mismo no hay `billing_service` que avisar.
"""

import base64
import json
import logging
import time

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MIME_ACEPTADOS = {"image/jpeg", "image/png", "image/webp"}


class GeminiError(Exception):
    pass


class ElementoMedido(BaseModel):
    """Un elemento reconocido, con su medida real estimada.

    `box_2d` viaja tal cual lo da Gemini ([ymin, xmin, ymax, xmax] en 0-1000):
    convertirlo a píxeles es cosa del cliente, que es quien conoce el tamaño
    con el que finalmente pinta la imagen.
    """

    label: str
    box_2d: list[int]
    ancho_cm: float | None = None
    alto_cm: float | None = None
    es_referencia: bool = False
    confianza: str | None = None


class MetricasIA(BaseModel):
    """Coste y latencia de la llamada, para poder comparar proveedores desde
    la propia pantalla en vez de a ciegas."""

    proveedor: str
    modelo: str
    ms: int
    tokens_entrada: int = 0
    tokens_salida: int = 0
    #: DeepSeek de visión es un modelo de razonamiento: parte de los tokens de
    #: salida se van en pensar antes de responder, y esa parte se paga igual.
    #: Gemini no desglosa esto, así que aquí va a 0.
    tokens_razonamiento: int = 0


class ResultadoEscalaOut(BaseModel):
    elementos: list[ElementoMedido] = []
    referencia: str | None = None
    razonamiento: str | None = None
    mensaje: str | None = None
    metricas: MetricasIA | None = None


class MedidaEntrePuntosOut(BaseModel):
    distancia_cm: float | None = None
    referencia: str | None = None
    razonamiento: str | None = None
    confianza: str | None = None
    mensaje: str | None = None


_PROMPT = (
    "Eres un asistente de mediciones de obra en España. Analiza esta foto de "
    "un espacio y devuelve las DIMENSIONES REALES de los elementos "
    "constructivos que reconozcas.\n\n"
    "Procede así:\n"
    "1. Busca primero un elemento de tamaño normalizado o muy estandarizado "
    "que te sirva de referencia de escala. Por orden de fiabilidad: una hoja "
    "de puerta de paso (en España, típicamente 203 cm de alto y 72,5-82,5 cm "
    "de ancho), un enchufe o interruptor (marco de ~8 cm), un ladrillo cara "
    "vista (24 × 11,5 × 5 cm), una baldosa o plaqueta de formato de fábrica, "
    "un escalón (huella ~28 cm, contrahuella ~18 cm), un peldaño, una "
    "encimera (85-90 cm de altura), un inodoro, una puerta de ascensor. "
    "Márcalo con \"es_referencia\": true e indica en \"razonamiento\" qué "
    "medida real le has asignado y por qué.\n"
    "2. Con esa referencia, estima el ancho y el alto REALES en centímetros "
    "de los demás elementos relevantes (paredes, huecos, ventanas, puertas, "
    "vigas, pilares, tramos de tabique...).\n\n"
    "MUY IMPORTANTE sobre la perspectiva: no apliques una única escala de "
    "píxeles a toda la imagen. Un elemento que está al fondo se ve más "
    "pequeño que uno cercano aunque midan lo mismo — corrige eso en tu "
    "estimación de cada elemento por separado, teniendo en cuenta a qué "
    "profundidad está respecto a la referencia. Si un elemento está muy "
    "escorzado o cortado por el borde de la foto y su medida no es fiable, "
    "omite esa dimensión (déjala a null) en vez de inventarla.\n\n"
    "Devuelve el cuadro delimitador de cada elemento como \"box_2d\": "
    "[ymin, xmin, ymax, xmax], enteros normalizados a 0-1000 respecto al alto "
    "y al ancho de la imagen, con el origen en la esquina superior "
    "izquierda.\n\n"
    "Indica en \"confianza\" de cada elemento: \"alta\" si su medida se apoya "
    "directamente en la referencia y está en su mismo plano, \"media\" si has "
    "tenido que corregir perspectiva o profundidad, \"baja\" si es poco más "
    "que una estimación.\n\n"
    "Si no encuentras NADA que sirva de referencia de escala fiable, "
    "devuelve la lista de elementos vacía y explica por qué en \"mensaje\" — "
    "no inventes medidas sin referencia.\n\n"
    "Responde exclusivamente con un JSON con este esquema exacto, sin texto "
    'adicional: {"elementos": [{"label": string, "box_2d": [number, number, '
    'number, number], "ancho_cm": number o null, "alto_cm": number o null, '
    '"es_referencia": boolean, "confianza": "alta"|"media"|"baja"}], '
    '"referencia": string o null, "razonamiento": string o null, "mensaje": '
    "string o null}"
)


def _parsear(contenido: str, proveedor: str) -> ResultadoEscalaOut:
    if not contenido.strip():
        # Le pasa a DeepSeek de visión: agota el presupuesto de tokens
        # razonando y corta antes de escribir el JSON. Sin este aviso, en la
        # pantalla solo se vería "no ha encontrado nada", que despista.
        raise GeminiError(
            f"{proveedor} no llegó a responder: agotó el presupuesto de tokens razonando "
            "antes de emitir el resultado. Prueba con una foto más sencilla o con el otro proveedor."
        )
    try:
        bruto = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"{proveedor} no devolvió un JSON válido: {exc}") from exc
    try:
        resultado = ResultadoEscalaOut.model_validate(bruto)
    except ValidationError as exc:
        raise GeminiError(
            f"La respuesta de {proveedor} no encaja en el esquema esperado: {exc}"
        ) from exc
    # Una caja mal formada estropea el dibujo en el cliente; mejor descartar
    # ese elemento que pintar un rectángulo imposible sobre la foto.
    resultado.elementos = [e for e in resultado.elementos if len(e.box_2d) == 4]
    return resultado


async def detectar_escala(contenido: bytes, mime_type: str) -> ResultadoEscalaOut:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiError("Gemini no tiene clave configurada (GEMINI_API_KEY en el .env)")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(contenido).decode(),
                        }
                    },
                ]
            }
        ],
        # `temperature` a 0: esto es una lectura, no una redacción — interesa
        # que la misma foto dé la misma medida dos veces seguidas.
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    arranque = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60.0) as cliente:
            respuesta = await cliente.post(
                f"{settings.gemini_base_url.rstrip('/')}/models/{settings.gemini_model}:generateContent",
                json=payload,
                headers={"X-goog-api-key": settings.gemini_api_key},
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fallo al llamar a Gemini: %s", exc)
        raise GeminiError(f"No se pudo contactar con Gemini: {exc}") from exc
    ms = int((time.monotonic() - arranque) * 1000)

    cuerpo = respuesta.json()
    try:
        texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GeminiError(f"Respuesta de Gemini sin contenido interpretable: {cuerpo}") from exc

    resultado = _parsear(texto, "Gemini")
    uso = cuerpo.get("usageMetadata", {})
    resultado.metricas = MetricasIA(
        proveedor="gemini",
        modelo=settings.gemini_model,
        ms=ms,
        tokens_entrada=int(uso.get("promptTokenCount", 0)),
        tokens_salida=int(uso.get("candidatesTokenCount", 0)),
    )
    return resultado


# DeepSeek de visión viene con el modo PENSANTE activado por defecto, y para
# esta tarea es un mal negocio: medido, gastaba ~8.700 tokens razonando, tardaba
# 76-100 s y a menudo agotaba el presupuesto ANTES de emitir el JSON (devolvía
# contenido vacío). Apagarlo con `thinking: disabled` (parámetro documentado en
# https://api-docs.deepseek.com/guides/thinking_mode/) lo deja en ~2,8 s y
# ~1.285 tokens, con las cajas igual de precisas o más.
#
# Además, el modo pensante IGNORA `temperature` — así que apagarlo es también
# lo que hace que el `temperature: 0` de abajo sirva de algo y que la misma
# foto dé el mismo resultado dos veces.
DEEPSEEK_SIN_PENSAR = {"type": "disabled"}
DEEPSEEK_MAX_TOKENS = 4000


async def detectar_escala_deepseek(contenido: bytes, mime_type: str) -> ResultadoEscalaOut:
    """Misma tarea que `detectar_escala`, contra DeepSeek en vez de Gemini.

    La API de DeepSeek es compatible con la de OpenAI, así que la imagen no va
    como `inline_data` (formato de Gemini) sino como un `image_url` con un
    data: URI en base64. La clave y la `base_url` son las MISMAS que las del
    modelo de texto: lo único que cambia es qué `model` se manda.
    """
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise GeminiError("DeepSeek no tiene clave configurada (DEEPSEEK_API_KEY en el .env)")

    payload = {
        "model": settings.deepseek_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"text": _PROMPT, "type": "text"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64.b64encode(contenido).decode()}"
                        },
                    },
                ],
            }
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": DEEPSEEK_MAX_TOKENS,
        "temperature": 0,
        "thinking": DEEPSEEK_SIN_PENSAR,
    }
    arranque = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60.0) as cliente:
            respuesta = await cliente.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fallo al llamar a DeepSeek: %s", exc)
        raise GeminiError(f"No se pudo contactar con DeepSeek: {exc}") from exc
    ms = int((time.monotonic() - arranque) * 1000)

    cuerpo = respuesta.json()
    try:
        texto = cuerpo["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise GeminiError(f"Respuesta de DeepSeek sin contenido interpretable: {cuerpo}") from exc

    resultado = _parsear(texto, "DeepSeek")
    uso = cuerpo.get("usage", {})
    resultado.metricas = MetricasIA(
        proveedor="deepseek",
        modelo=settings.deepseek_vision_model,
        ms=ms,
        tokens_entrada=int(uso.get("prompt_tokens", 0)),
        tokens_salida=int(uso.get("completion_tokens", 0)),
        tokens_razonamiento=int(
            (uso.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        ),
    )
    return resultado
