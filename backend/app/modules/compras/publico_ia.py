"""Lectura con IA del documento de precios que sube el proveedor.

Un solo turno con JSON forzado, calcado del patrón de `ia/gemini.leer_plano`:
se le manda la lista de lo que se le pide (sin ningún precio del emisor) más
su documento, y devuelve un precio por línea.

**Lo paga el emisor.** El contexto público está fijado a su organización, así
que `registrar_uso_ia(organization_id=ctx.organization_id, ...)` carga el
consumo donde toca por construcción, no por acordarse de pasarlo.
"""

import base64
import json
import logging
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ia.credenciales import credenciales_gemini
from app.modules.ia.gemini import MIME_EXCEL, GeminiError, UsoTokens, tabla_de_excel

logger = logging.getLogger("obras.compras.publico_ia")

# Tope de tamaño del documento. El endpoint es público: sin esto, una sola
# petición puede reventar la memoria del proceso.
MAX_BYTES = 8 * 1024 * 1024

MIME_ACEPTADOS = {"application/pdf", "text/plain", "text/csv"} | MIME_EXCEL

_PROMPT = """Eres un aparejador que está pasando a limpio la oferta de un proveedor.

Te doy una lista de partidas sobre las que se le ha pedido precio, y el
documento que ha mandado el proveedor con sus precios.

Devuelve SOLO un JSON con esta forma exacta:
{"lineas": [{"id": "<el id que te doy>", "precio": <número>}]}

Reglas:
- `precio` es el PRECIO UNITARIO (por unidad de medida de la partida), nunca
  el importe total. Si en el documento solo aparece el total, divídelo entre
  la medición que te doy.
- Usa punto decimal. Sin símbolo de moneda, sin separador de miles.
- Incluye SOLO las partidas cuyo precio encuentres con seguridad razonable.
  Si de una no estás seguro, déjala fuera: es mejor que la rellene a mano.
- No inventes partidas ni ids: usa exactamente los que te doy.
"""


def _lineas_para_prompt(lineas: list[dict]) -> str:
    return "\n".join(
        f"- id={l['id']} | {l['resumen']} | unidad: {l['unidad']} | medición: {l['medicion']}"
        for l in lineas
    )


async def leer_precios(
    session: AsyncSession,
    *,
    contenido: bytes,
    mime_type: str,
    nombre: str,
    lineas: list[dict],
) -> tuple[dict[str, Decimal], UsoTokens]:
    """Devuelve `({id_de_linea: precio}, uso)`. Solo las que haya sabido leer."""
    credenciales = await credenciales_gemini(session)
    if not credenciales.api_key:
        raise GeminiError(
            "La lectura automática no está disponible: la organización que te "
            "ha pedido precio no tiene la IA configurada."
        )

    contexto = f"{_PROMPT}\n\nPartidas sobre las que se pide precio:\n{_lineas_para_prompt(lineas)}"

    partes: list[dict] = [{"text": contexto}]
    if mime_type in MIME_EXCEL:
        # Gemini no entiende una hoja de cálculo como `inline_data`: se
        # convierte a tabla de texto antes de mandarla (igual que `leer_plano`).
        partes.append({"text": f"\n\nDocumento «{nombre}»:\n{tabla_de_excel(contenido)}"})
    elif mime_type.startswith("text/"):
        partes.append(
            {"text": f"\n\nDocumento «{nombre}»:\n{contenido.decode('utf-8', errors='replace')}"}
        )
    else:
        partes.append(
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(contenido).decode(),
                }
            }
        )

    payload = {
        "contents": [{"parts": partes}],
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
        logger.warning("Fallo al llamar a Gemini leyendo la oferta: %s", exc)
        raise GeminiError(f"No se pudo contactar con Gemini: {exc}") from exc

    cuerpo = respuesta.json()
    try:
        texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise GeminiError(f"Respuesta de Gemini sin contenido interpretable: {cuerpo}") from exc

    uso_bruto = cuerpo.get("usageMetadata", {})
    uso = UsoTokens(
        modelo=credenciales.modelo,
        tokens_entrada=int(uso_bruto.get("promptTokenCount", 0)),
        tokens_salida=int(uso_bruto.get("candidatesTokenCount", 0)),
    )

    # Los ids válidos se comprueban aquí y no se dan por buenos: el modelo
    # puede devolver cualquier cosa, y lo que salga de aquí acaba escribiendo
    # en base de datos.
    validos = {l["id"] for l in lineas}
    precios: dict[str, Decimal] = {}
    try:
        datos = json.loads(texto)
        for entrada in datos.get("lineas", []):
            id_linea = str(entrada.get("id", ""))
            if id_linea not in validos:
                continue
            try:
                precio = Decimal(str(entrada["precio"]))
            except (InvalidOperation, KeyError, TypeError):
                continue
            if precio < 0:
                continue
            precios[id_linea] = precio
    except (json.JSONDecodeError, AttributeError) as exc:
        raise GeminiError(f"Gemini devolvió algo que no es el JSON esperado: {texto[:200]}") from exc

    return precios, uso
