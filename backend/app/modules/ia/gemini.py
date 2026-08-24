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
import uuid
from dataclasses import dataclass

import httpx
import openpyxl
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import require_organization_id
from app.modules.ia.credenciales import credenciales_gemini
from app.modules.ia.schemas import (
    CapituloPropuestoOut,
    LineaMedicionSugeridaOut,
    LineaSugeridaLLM,
    PropuestaAccionOut,
    RespuestaLecturaPlanoLLM,
)
from app.modules.presupuestos import presupuesto_calculo as calc

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


def _prompt_documento(permite_importar: bool, partida_destino: dict | None = None) -> str:
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
    texto = (
        base
        + " Si el documento trae una relación de partidas/conceptos con "
        "precio (un presupuesto de proveedor, una oferta, un albarán con "
        "precios...) y el usuario pide colgarlo del presupuesto, añadirlo, "
        "importarlo o meterlo en un capítulo aparte, usa "
        "`proponer_importar_capitulo` con cada línea que puedas leer con "
        "claridad — resumen, unidad y precio tal cual figuran en el "
        "documento, sin inventar ni redondear lo que no se lea bien (omite "
        "esa línea si el precio o la unidad no son legibles). "
        "\n\nSi en cambio el documento NO trae precios (un plano acotado, una "
        "memoria técnica, unas cotas...) y el usuario pide volcar, incorporar "
        "o presupuestar lo que hay en él, NO propongas precio 0€ ni te "
        "limites a decir que faltan precios: calcula primero las mediciones a "
        "partir de las cotas (como ya sabes hacer) y luego, en UNA sola "
        "llamada a `buscar_conceptos_banco`, manda TODOS los términos de "
        "todas las partidas que hayas identificado (el parámetro `textos` es "
        "una lista — no llames a la herramienta una vez por partida, tienes "
        "un número limitado de turnos y cada llamada de más resta margen "
        "para poder terminar). Con lo que encuentres, usa "
        "`proponer_capitulos`: cada partida nueva lleva su "
        "descompuesto con los componentes reales que hayas encontrado "
        "(dales su `concepto_id` exacto, nunca inventado) y, para lo que de "
        "verdad no exista en el banco, un componente personalizado con un "
        "precio de mercado razonable — dilo claramente en la descripción, no "
        "lo des como precio real. Añade también `texto` en cada partida "
        "nueva con la explicación técnica (de qué trata, cómo se ha medido) "
        "— es la descripción ampliada de la partida, no un dato del "
        "descompuesto. NO te quedes solo con el precio y el descompuesto: "
        "añade además `mediciones` en cada partida nueva con las mismas "
        "cantidades que ya has calculado de las cotas (una línea por cada "
        "elemento medible), para que la partida quede con su medición real "
        "en vez de en 0 — es el mismo cálculo que ya has hecho para elegir "
        "qué buscar en el banco, no lo descartes al proponer. Solo si una "
        "partida no tiene ningún componente razonable ni en el banco ni por "
        "precio de mercado, dilo en la conversación en vez de inventar. "
        "\n\nEn los dos casos: no es una acción real todavía, solo propones "
        "— el usuario confirma después en la pantalla. Nunca digas que ya lo "
        "has creado, guardado o buscado en el banco sin haberlo hecho de "
        "verdad con la herramienta correspondiente."
    )
    if partida_destino:
        texto += (
            f"\n\nEsta conversación se ha abierto sobre una partida ya "
            f"existente del presupuesto: «{partida_destino['resumen']}» "
            f"(unidad: {partida_destino['unidad']}). Si el documento es un "
            f"plano acotado, una memoria técnica o unas cotas que "
            f"corresponden a ESE mismo elemento y el usuario pide sus "
            f"mediciones, usa `proponer_mediciones_partida` para añadírselas "
            f"a esta partida — NO crees una partida nueva con "
            f"`proponer_capitulos` para esto, ya existe. Reserva "
            f"`proponer_importar_capitulo` y `proponer_capitulos` para "
            f"cuando el documento traiga trabajo claramente distinto al de "
            f"esta partida (otra fase, otro capítulo)."
        )
    return texto


_DECLARACION_IMPORTAR_CAPITULO = {
    "name": "proponer_importar_capitulo",
    "description": (
        "Propón crear un capítulo nuevo en el presupuesto actual con las "
        "partidas leídas del documento, TAL CUAL vienen con su precio en "
        "el propio documento (una oferta, un presupuesto de proveedor...). "
        "No crea nada todavía: solo deja lista la propuesta para que el "
        "usuario la confirme."
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

_DECLARACION_BUSCAR_CONCEPTOS_BANCO = {
    "name": "buscar_conceptos_banco",
    "description": (
        "Busca conceptos del banco de precios de esta cuenta (materiales, "
        "mano de obra, maquinaria...) por código o descripción — hace falta "
        "para tener el id exacto de un componente antes de proponer un "
        "capítulo con precios reales, cuando el documento no trae precio "
        "propio (un plano, unas cotas). Manda TODOS los términos que "
        "necesites de una vez en `textos` (uno por cada partida o "
        "componente que quieras buscar, por ejemplo con un plano de "
        "cimentación: [\"excavación pozos\", \"excavación zanjas\", "
        "\"hormigón limpieza\", \"hormigón armado zapatas\", \"acero "
        "corrugado\"...]) — NO llames a esta herramienta varias veces "
        "seguidas para términos distintos, agrúpalos en una sola llamada. "
        "Devuelve como mucho 10 resultados por término; si un término no "
        "trae nada, prueba con uno más genérico en la siguiente llamada."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "textos": {
                "type": "ARRAY",
                "description": "Todos los términos a buscar, uno por partida o componente",
                "items": {"type": "STRING"},
            },
        },
        "required": ["textos"],
    },
}

# Mismo esquema que `asistente._ESQUEMA_COMPONENTE`, en el formato de tipos
# de Gemini (mayúsculas) en vez del que usa DeepSeek — ver esa constante
# para el porqué de cada campo.
_ESQUEMA_COMPONENTE_GEMINI = {
    "type": "OBJECT",
    "properties": {
        "concepto_id": {
            "type": "STRING",
            "description": "uuid del concepto (de buscar_conceptos_banco) — omite esto si personalizado es true",
        },
        "rendimiento": {
            "type": "NUMBER",
            "description": "Cantidad de este componente por unidad de la partida",
        },
        "personalizado": {
            "type": "BOOLEAN",
            "description": (
                "true si este componente no está en el banco y usas un precio de "
                "mercado razonable en su lugar. Rellena resumen/unidad/precio/"
                "naturaleza en vez de concepto_id."
            ),
        },
        "resumen": {
            "type": "STRING",
            "description": "Descripción del componente personalizado (solo si personalizado es true)",
        },
        "unidad": {
            "type": "STRING",
            "description": "Unidad del componente personalizado: h, ud, m2... (solo si personalizado es true)",
        },
        "precio": {
            "type": "NUMBER",
            "description": "Precio unitario del componente personalizado (solo si personalizado es true)",
        },
        "naturaleza": {
            "type": "STRING",
            "enum": ["mano_obra", "material", "maquinaria", "servicio", "otro"],
            "description": "Tipo de recurso del componente personalizado (solo si personalizado es true)",
        },
    },
    "required": ["rendimiento"],
}

# Compartido entre `proponer_mediciones_partida` (partida existente) y
# `proponer_capitulos` (partida nueva, dentro de un capítulo) — misma forma
# de línea en los dos casos.
_ESQUEMA_LINEA_MEDICION_GEMINI = {
    "type": "OBJECT",
    "properties": {
        "comentario": {
            "type": "STRING",
            "description": "Qué es (p. ej. nombre de la estancia o tramo)",
        },
        "uds": {"type": "NUMBER"},
        "longitud": {"type": "NUMBER"},
        "anchura": {"type": "NUMBER"},
        "altura": {"type": "NUMBER"},
    },
}

_DECLARACION_PROPONER_CAPITULOS = {
    "name": "proponer_capitulos",
    "description": (
        "Propón uno o varios capítulos nuevos en el presupuesto, cada "
        "partida con su descompuesto REAL resuelto contra el banco de "
        "precios (o con un componente personalizado a precio de mercado "
        "para lo que no encuentres) — la vía para presupuestar algo que no "
        "trae precio propio en el documento (un plano, unas cotas). Busca "
        "los componentes antes con `buscar_conceptos_banco`; no inventes un "
        "concepto_id. Si el documento es un plano acotado, calcula también "
        "`mediciones` para cada partida nueva a partir de sus cotas — sin "
        "esto la partida se queda con medición 0 y el usuario tiene que "
        "medirla a mano después, que es justo lo que se le está evitando "
        "al leerle el plano."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "capitulos": {
                "type": "ARRAY",
                "description": "Todos los capítulos a proponer, en el orden en que deben quedar",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "capitulo_resumen": {"type": "STRING", "description": "Nombre del capítulo"},
                        "partidas": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "resumen": {"type": "STRING", "description": "Descripción de la partida"},
                                    "unidad": {
                                        "type": "STRING",
                                        "description": "Unidad de medida: ud, m2, m, m3, kg...",
                                    },
                                    "componentes": {
                                        "type": "ARRAY",
                                        "description": "Componentes de su descompuesto",
                                        "items": _ESQUEMA_COMPONENTE_GEMINI,
                                    },
                                    "texto": {
                                        "type": "STRING",
                                        "description": "Descripción ampliada de la partida (de qué trata, cómo se ha medido) — no un dato del descompuesto",
                                    },
                                    "mediciones": {
                                        "type": "ARRAY",
                                        "description": (
                                            "Líneas de medición de esta partida, calculadas a "
                                            "partir de las cotas del plano (una línea por cada "
                                            "elemento medible: un tramo, una unidad repetida...) "
                                            "— sin esto la partida se crea con medición 0."
                                        ),
                                        "items": _ESQUEMA_LINEA_MEDICION_GEMINI,
                                    },
                                },
                                "required": ["resumen", "unidad", "componentes"],
                            },
                        },
                    },
                    "required": ["capitulo_resumen", "partidas"],
                },
            },
            "descripcion": {
                "type": "STRING",
                "description": "Frase corta resumiendo el plan: cuántos capítulos y qué llevan",
            },
        },
        "required": ["capitulos", "descripcion"],
    },
}

# Compartido entre `proponer_mediciones_partida` (partida existente) y
# `proponer_capitulos` (partida nueva, dentro de un capítulo) — misma forma
# de línea en los dos casos.
_DECLARACION_PROPONER_MEDICIONES = {
    "name": "proponer_mediciones_partida",
    "description": (
        "Propón líneas de medición para la partida YA EXISTENTE sobre la "
        "que se abrió esta conversación — no crea ninguna partida nueva, "
        "solo añade líneas a su estado de mediciones. Es la vía para cuando "
        "el documento es un plano acotado con las cotas de ese mismo "
        "elemento. No inventes cotas que no estén en el plano: si una "
        "medida no es legible o no aplica, omite ese campo en vez de "
        "rellenarlo."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "lineas": {
                "type": "ARRAY",
                "description": (
                    "Una línea por cada elemento medible (un tramo de muro, "
                    "una estancia...)"
                ),
                "items": _ESQUEMA_LINEA_MEDICION_GEMINI,
            },
            "descripcion": {
                "type": "STRING",
                "description": "Frase corta resumiendo cuántas líneas propones y de qué",
            },
        },
        "required": ["lineas"],
    },
}


def _herramientas_documento(partida_destino: dict | None) -> list[dict]:
    declaraciones = [
        _DECLARACION_IMPORTAR_CAPITULO,
        _DECLARACION_BUSCAR_CONCEPTOS_BANCO,
        _DECLARACION_PROPONER_CAPITULOS,
    ]
    if partida_destino:
        declaraciones.append(_DECLARACION_PROPONER_MEDICIONES)
    return [{"functionDeclarations": declaraciones}]

# Con `textos` aceptando una lista (Fase 51b), una búsqueda ya cubre TODAS
# las partidas de golpe — pero un plano complejo puede necesitar algún turno
# extra de puro razonamiento visual (contar zapatas, leer una cota) antes de
# llegar a buscar nada, así que el margen se deja generoso de todos modos.
MAX_TURNOS_DOCUMENTO = 14


async def chat_documento(
    session: AsyncSession,
    documentos: list[tuple[bytes, str]],
    mensajes: list[dict],
    *,
    permitir_propuesta: bool = False,
    partida_destino: dict | None = None,
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
    presupuesto concreto al que colgarle lo que proponga. `partida_destino`
    (Fase 51c), cuando el documento se soltó sobre una partida ya existente,
    activa además `proponer_mediciones_partida` — añadir líneas de medición
    a esa partida en vez de crear una nueva."""
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
        "systemInstruction": {
            "parts": [{"text": _prompt_documento(permitir_propuesta, partida_destino)}]
        },
        "contents": contents,
    }
    if permitir_propuesta:
        payload["tools"] = _herramientas_documento(partida_destino)

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

    tokens_entrada = 0
    tokens_salida = 0
    propuesta: PropuestaAccionOut | None = None
    texto = ""

    async def _ejecutar_herramienta(
        nombre: str, argumentos: dict
    ) -> tuple[dict, PropuestaAccionOut | None, bool]:
        """Una llamada de función ya identificada — devuelve la respuesta a
        meter en `functionResponse`, la propuesta si esta llamada la cierra,
        y si esta llamada es TERMINAL (propone) o no (`buscar_conceptos_banco`,
        que sigue la conversación)."""
        if nombre == "buscar_conceptos_banco":
            from app.modules.ia.asistente import buscar_conceptos_banco

            # Un término por partida, pero UNA sola llamada para todos: si
            # cada búsqueda gastara su propio turno, un documento de 8
            # partidas agotaría el límite de turnos antes de poder proponer
            # nada — el motivo de que este parámetro sea plural.
            textos = argumentos.get("textos") or ([argumentos["texto"]] if argumentos.get("texto") else [])
            resultados_por_termino = {
                texto: await buscar_conceptos_banco(session, texto) for texto in textos
            }
            return {"resultados_por_termino": resultados_por_termino}, None, False

        if nombre == "proponer_importar_capitulo":
            try:
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
            return {"ok": propuesta is not None}, propuesta, True

        if nombre == "proponer_capitulos":
            from app.modules.ia.asistente import resolver_partida_item

            org_id = require_organization_id()
            brutos_capitulos = argumentos.get("capitulos") or []
            capitulos_ok: list[CapituloPropuestoOut] = []
            capitulos_con_error: list[str] = []
            for bruto_capitulo in brutos_capitulos:
                resumen_capitulo = bruto_capitulo.get("capitulo_resumen")
                brutos_partidas = bruto_capitulo.get("partidas") or []
                if not resumen_capitulo or not brutos_partidas:
                    capitulos_con_error.append(f"capítulo incompleto: {bruto_capitulo}")
                    continue
                partidas_ok = []
                partidas_con_error = []
                for bruto_partida in brutos_partidas:
                    item, error = await resolver_partida_item(session, org_id, bruto_partida)
                    if item is not None:
                        partidas_ok.append(item)
                    else:
                        partidas_con_error.append(error or "partida inválida")
                if not partidas_ok:
                    capitulos_con_error.append(
                        f"«{resumen_capitulo}»: ninguna partida válida ({partidas_con_error})"
                    )
                    continue
                capitulos_ok.append(
                    CapituloPropuestoOut(resumen=resumen_capitulo, partidas=partidas_ok)
                )
            propuesta = None
            if capitulos_ok:
                total_partidas = sum(len(c.partidas) for c in capitulos_ok)
                propuesta = PropuestaAccionOut(
                    tipo="crear_capitulos",
                    capitulos_propuestos=capitulos_ok,
                    descripcion=argumentos.get("descripcion")
                    or f"Crear {len(capitulos_ok)} capítulo(s) con {total_partidas} partidas",
                )
            return (
                {"ok": propuesta is not None, "capitulos_con_error": capitulos_con_error or None},
                propuesta,
                True,
            )

        if nombre == "proponer_mediciones_partida":
            if partida_destino is None:
                return {"error": "No hay partida de destino en esta conversación"}, None, False
            brutos = argumentos.get("lineas") or []
            try:
                lineas_llm = [LineaSugeridaLLM.model_validate(l) for l in brutos]
            except ValidationError as exc:
                logger.warning(
                    "Mediciones propuestas por Gemini con forma inesperada: %s (%s)", brutos, exc
                )
                return {"error": "Formato de líneas inválido"}, None, False
            mediciones = [
                LineaMedicionSugeridaOut(
                    comentario=l.comentario,
                    uds=l.uds,
                    longitud=l.longitud,
                    anchura=l.anchura,
                    altura=l.altura,
                    parcial=calc.parcial_de(l.uds, l.longitud, l.anchura, l.altura),
                )
                for l in lineas_llm
            ]
            propuesta = None
            if mediciones:
                propuesta = PropuestaAccionOut(
                    tipo="anadir_mediciones_partida",
                    descripcion=argumentos.get("descripcion")
                    or f"Añadir {len(mediciones)} línea(s) de medición a «{partida_destino['resumen']}»",
                    partida_id=uuid.UUID(partida_destino["id"]),
                    mediciones_propuestas=mediciones,
                )
            return {"ok": propuesta is not None}, propuesta, True

        # Herramienta desconocida: no debería pasar (solo se declaran las de
        # arriba), pero mejor devolvérselo al modelo que reventar la
        # conversación entera por una llamada rara.
        return {"error": f"Herramienta desconocida: {nombre}"}, None, False

    # Bucle acotado (Fase 51): a diferencia de la única llamada de antes,
    # `buscar_conceptos_banco` es una herramienta INTERMEDIA — el modelo
    # busca, lee el resultado y decide si busca otra vez o ya propone. Solo
    # las herramientas que proponen (`proponer_importar_capitulo`,
    # `proponer_capitulos`) cierran la conversación con un turno de cierre
    # sin herramientas.
    #
    # Gemini puede pedir VARIAS llamadas a la vez en un mismo turno
    # ("parallel function calling") — y aquí es el caso normal, no la
    # excepción: un plano con seis partidas distintas dispara sus seis
    # búsquedas de golpe en vez de una por turno. Hay que leer y responder a
    # TODAS las de un turno antes de seguir (Gemini exige una
    # `functionResponse` por cada `functionCall` que hizo), o la
    # conversación se queda coja y agota los turnos sin avanzar.
    for turno in range(MAX_TURNOS_DOCUMENTO):
        activo = dict(payload, contents=contents)
        if turno == MAX_TURNOS_DOCUMENTO - 1:
            # Último turno permitido sin herramientas: si para entonces no ha
            # propuesto ni contestado, se le obliga a cerrar en texto en vez
            # de dejarlo pedir una búsqueda más.
            activo["tools"] = []
        cuerpo = await _llamar(activo)
        try:
            partes_respuesta = cuerpo["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            raise GeminiError(
                f"Respuesta de Gemini sin contenido interpretable: {cuerpo}"
            ) from exc

        uso_bruto = cuerpo.get("usageMetadata", {})
        tokens_entrada += int(uso_bruto.get("promptTokenCount", 0))
        tokens_salida += int(uso_bruto.get("candidatesTokenCount", 0))

        llamadas = [p for p in partes_respuesta if p.get("functionCall")]
        if not llamadas:
            texto = next((p.get("text", "") for p in partes_respuesta if "text" in p), "")
            break

        respuestas_funcion = []
        terminal = False
        for parte_llamada in llamadas:
            llamada = parte_llamada["functionCall"]
            nombre = llamada.get("name")
            argumentos = llamada.get("args") or {}
            respuesta_funcion, propuesta_de_esta, es_terminal = await _ejecutar_herramienta(
                nombre, argumentos
            )
            respuestas_funcion.append(
                {"functionResponse": {"name": nombre, "response": respuesta_funcion}}
            )
            if es_terminal:
                terminal = True
                propuesta = propuesta_de_esta

        contents.append({"role": "model", "parts": llamadas})
        contents.append({"role": "user", "parts": respuestas_funcion})

        if not terminal:
            continue  # sigue buscando o decide proponer, con herramientas otra vez

        # Turno de cierre sin herramientas para que redacte la frase que
        # acompaña a la propuesta — Gemini exige que se le devuelva cada
        # `functionCall` (con su `thoughtSignature`) tal cual antes de seguir
        # la conversación, igual que cualquier otro proveedor con
        # function-calling: https://ai.google.dev/gemini-api/docs/thought-signatures
        cuerpo2 = await _llamar({**payload, "contents": contents, "tools": []})
        uso_bruto2 = cuerpo2.get("usageMetadata", {})
        tokens_entrada += int(uso_bruto2.get("promptTokenCount", 0))
        tokens_salida += int(uso_bruto2.get("candidatesTokenCount", 0))
        try:
            texto = cuerpo2["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            texto = propuesta.descripcion if propuesta else "No he podido preparar la propuesta."
        break
    else:
        texto = (
            "No he terminado de resolverlo en los pasos que tengo permitidos. "
            "Prueba a preguntar de forma más concreta, o con menos partidas a la vez."
        )

    tokens = UsoTokens(
        modelo=credenciales.modelo, tokens_entrada=tokens_entrada, tokens_salida=tokens_salida
    )
    return texto.strip(), propuesta, tokens
