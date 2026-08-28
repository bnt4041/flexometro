"""Revisión con IA de una planta levantada en AR: a partir de las fotos que se
tomaron en cada esquina y de la geometría que midió el AR, devuelve qué
elementos (puertas, ventanas, huecos...) hay en cada muro y dónde.

Reparto de responsabilidades, que aquí no es un detalle:

- **La geometría NO se toca.** Las longitudes vienen del seguimiento 3D de
  ARCore, que mide en metros reales; la IA estima mirando una foto plana. Si
  se la dejara "corregir" las medidas, las empeoraría. Por eso el esquema de
  respuesta no admite longitudes de muro: solo elementos.
- **La IA aporta lo que el AR no sabe:** qué es cada cosa. Reconocer una
  puerta en una foto y situarla a lo largo del muro es justo lo que sí hace
  bien (ver `escala.py` sobre la precisión de `box_2d`).

Si la IA ve algo que no cuadra con la geometría medida, lo dice en
`observaciones` — avisar es útil, sobrescribir no.
"""

import base64
import json
import logging
import time

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.modules.testmeter.escala import (
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_SIN_PENSAR,
    GeminiError,
    MetricasIA,
)

logger = logging.getLogger(__name__)


class ElementoEnMuro(BaseModel):
    """Un elemento situado sobre uno de los muros de la planta."""

    #: Índice del muro (0 = el que va del vértice 0 al 1, y así).
    muro: int
    tipo: str
    ancho_cm: float | None = None
    alto_cm: float | None = None
    #: Dónde empieza el elemento a lo largo del muro, de 0 (vértice inicial) a
    #: 1 (vértice final). Con el ancho basta para dibujarlo sobre la pared.
    desde: float = Field(ge=0, le=1)
    hasta: float = Field(ge=0, le=1)
    confianza: str | None = None


class RevisionPlantaOut(BaseModel):
    elementos: list[ElementoEnMuro] = []
    observaciones: str | None = None
    metricas: MetricasIA | None = None


def _prompt(muros: list[float], n_fotos: int) -> str:
    lista = "\n".join(
        f"- Muro {i}: {largo:.2f} m" for i, largo in enumerate(muros)
    )
    return (
        "Eres un asistente de levantamiento de planos de obra en España. Te "
        "paso la planta de un espacio que YA se ha medido con realidad "
        "aumentada, y las fotos que se tomaron dentro de él.\n\n"
        f"La planta es un polígono cerrado de {len(muros)} muros, con estas "
        f"longitudes ya medidas:\n{lista}\n\n"
        f"Tienes {n_fotos} foto(s), tomadas en orden, una en cada esquina del "
        "recorrido: la foto 1 se hizo al marcar la esquina 1, y así "
        "sucesivamente. Cada foto mira hacia esa esquina, así que en ella se "
        "ven normalmente los dos muros que confluyen ahí.\n\n"
        "IMPORTANTE — no cambies las medidas: las longitudes de arriba están "
        "medidas con sensores y son correctas. NO propongas longitudes de "
        "muro distintas. Tu trabajo es decir QUÉ HAY en cada muro.\n\n"
        "Para cada elemento constructivo que reconozcas en las fotos (puerta "
        "de paso, ventana, hueco de paso sin puerta, armario empotrado, "
        "pilar, radiador, puerta corredera...), indica:\n"
        "- `muro`: a cuál de los muros de arriba pertenece (su número). "
        "Apóyate en las longitudes para decidir: si en una foto ves una pared "
        "con una ventana y esa pared es claramente la más larga, será el muro "
        "más largo de la lista.\n"
        "- `tipo`: qué es, en una o dos palabras.\n"
        "- `ancho_cm` y `alto_cm`: sus dimensiones reales estimadas.\n"
        "- `desde` y `hasta`: en qué parte del muro está, como fracción de 0 "
        "a 1 de su longitud (0 = principio del muro, 1 = final). Por ejemplo, "
        "una puerta de 80 cm centrada en un muro de 4 m sería desde 0.4 hasta "
        "0.6.\n"
        "- `confianza`: \"alta\" si lo ves con claridad y sabes seguro en qué "
        "muro está, \"media\" si dudas del muro o de la medida, \"baja\" si "
        "es poco más que una suposición.\n\n"
        "No inventes elementos que no se vean en las fotos. Si un muro no "
        "aparece en ninguna foto, simplemente no devuelvas nada para él. Si "
        "algo no te cuadra con las longitudes medidas (por ejemplo, ves una "
        "pared que parece mucho más larga de lo que dice la lista), dilo en "
        "`observaciones` en vez de cambiar la medida.\n\n"
        "Responde exclusivamente con un JSON con este esquema exacto, sin "
        'texto adicional: {"elementos": [{"muro": number, "tipo": string, '
        '"ancho_cm": number o null, "alto_cm": number o null, "desde": '
        'number, "hasta": number, "confianza": "alta"|"media"|"baja"}], '
        '"observaciones": string o null}'
    )


def _parsear(contenido: str, proveedor: str, n_muros: int) -> RevisionPlantaOut:
    if not contenido.strip():
        raise GeminiError(
            f"{proveedor} no llegó a responder (se quedó sin margen de tokens). "
            "Prueba con menos fotos."
        )
    try:
        bruto = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"{proveedor} no devolvió un JSON válido: {exc}") from exc
    try:
        resultado = RevisionPlantaOut.model_validate(bruto)
    except ValidationError as exc:
        raise GeminiError(
            f"La respuesta de {proveedor} no encaja en el esquema esperado: {exc}"
        ) from exc
    # Un `muro` fuera de rango dibujaría el elemento sobre una pared que no
    # existe; y `desde > hasta` lo dibujaría del revés. Se descartan en vez de
    # arrastrar el error hasta el plano.
    resultado.elementos = [
        e
        for e in resultado.elementos
        if 0 <= e.muro < n_muros and e.desde < e.hasta
    ]
    return resultado


async def revisar_planta(
    fotos: list[tuple[bytes, str]], muros: list[float], proveedor: str
) -> RevisionPlantaOut:
    settings = get_settings()
    prompt = _prompt(muros, len(fotos))
    arranque = time.monotonic()

    if proveedor == "deepseek":
        if not settings.deepseek_api_key:
            raise GeminiError("DeepSeek no tiene clave configurada")
        contenido: list[dict] = [{"type": "text", "text": prompt}]
        for datos, mime in fotos:
            contenido.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{base64.b64encode(datos).decode()}"},
                }
            )
        payload = {
            "model": settings.deepseek_vision_model,
            "messages": [{"role": "user", "content": contenido}],
            "response_format": {"type": "json_object"},
            "max_tokens": DEEPSEEK_MAX_TOKENS,
            "temperature": 0,
            "thinking": DEEPSEEK_SIN_PENSAR,
        }
        url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
        cabeceras = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
        modelo = settings.deepseek_vision_model
    else:
        if not settings.gemini_api_key:
            raise GeminiError("Gemini no tiene clave configurada")
        partes: list[dict] = [{"text": prompt}]
        for datos, mime in fotos:
            partes.append(
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(datos).decode()}}
            )
        payload = {
            "contents": [{"parts": partes}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
        }
        url = f"{settings.gemini_base_url.rstrip('/')}/models/{settings.gemini_model}:generateContent"
        cabeceras = {"X-goog-api-key": settings.gemini_api_key}
        modelo = settings.gemini_model

    try:
        # Más generoso que en `escala.py`: aquí viajan varias fotos de golpe.
        async with httpx.AsyncClient(timeout=120.0) as cliente:
            respuesta = await cliente.post(url, json=payload, headers=cabeceras)
            respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Fallo al revisar la planta con %s: %s", proveedor, exc)
        raise GeminiError(f"No se pudo contactar con {proveedor}: {exc}") from exc
    ms = int((time.monotonic() - arranque) * 1000)

    cuerpo = respuesta.json()
    try:
        if proveedor == "deepseek":
            texto = cuerpo["choices"][0]["message"]["content"] or ""
            uso = cuerpo.get("usage", {})
            entrada = int(uso.get("prompt_tokens", 0))
            salida = int(uso.get("completion_tokens", 0))
            razonamiento = int((uso.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
        else:
            texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
            uso = cuerpo.get("usageMetadata", {})
            entrada = int(uso.get("promptTokenCount", 0))
            salida = int(uso.get("candidatesTokenCount", 0))
            razonamiento = 0
    except (KeyError, IndexError) as exc:
        raise GeminiError(f"Respuesta sin contenido interpretable: {cuerpo}") from exc

    resultado = _parsear(texto, proveedor, len(muros))
    resultado.metricas = MetricasIA(
        proveedor=proveedor,
        modelo=modelo,
        ms=ms,
        tokens_entrada=entrada,
        tokens_salida=salida,
        tokens_razonamiento=razonamiento,
    )
    return resultado
