"""Leer un plano con IA para no tener que calibrarlo a mano.

La decisión que sostiene este módulo: **a la IA no se le piden coordenadas.**
Un modelo estimando píxeles se equivoca un 2-5 %, y un 3 % de error en la
escala es un 3 % en todas las mediciones del plano y un 6 % en todas las
áreas. Eso no produce un error visible: produce un presupuesto equivocado que
nadie revisa porque «lo ha medido el programa».

Lo que sí se le pide es **leer el texto**, que es donde un modelo de visión es
bueno de verdad. Y con eso basta, porque la escala de un plano suele estar
escrita en el cajetín:

    «E 1:50» + una página A3 -> metros por unidad, exacto y sin estimar nada.

La cuenta es pura geometría del papel: un punto PDF son 25,4/72 mm sobre el
papel, y a escala 1:N cada milímetro de papel son N milímetros de obra. Cero
píxeles de por medio.

Cuando el plano no lleva escala escrita, se cae a la segunda opción: leer una
cota acotada («10,00 m») y proponerla. Esa sí necesita que alguien pinche los
dos extremos, porque el texto dice cuánto mide pero no dónde empieza.
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Un punto PDF en milímetros de papel. 72 puntos por pulgada, 25,4 mm por
#: pulgada — de aquí sale que un plano con escala escrita se calibre exacto.
MM_POR_PUNTO = Decimal("25.4") / Decimal(72)

MAX_TAMANO_IA = 15 * 1024 * 1024

#: Escalas de dibujo que se usan de verdad en construcción. Sirve de red: si
#: el modelo lee «1:57» es que ha leído mal, y aceptarlo calibraría el plano
#: entero con un número inventado.
ESCALAS_HABITUALES = frozenset(
    {1, 2, 5, 10, 20, 25, 33, 50, 75, 100, 125, 150, 200, 250, 500, 1000, 2000, 5000}
)


class LecturaFallida(Exception):
    pass


@dataclass
class CotaLeida:
    """Una cota acotada del plano. El valor es de fiar (es texto); dónde
    está, no — por eso vuelve como sugerencia y no como calibración."""

    texto: str
    metros: Decimal
    donde: str | None = None


@dataclass
class Lectura:
    #: El denominador de la escala impresa: 50 para «1:50». `None` si el plano
    #: no la lleva escrita o no se ha leído con seguridad.
    escala_impresa: int | None = None
    escala_texto: str | None = None
    cotas: list[CotaLeida] = field(default_factory=list)
    #: Qué ha visto del plano, en una línea. Para que la persona sepa que la
    #: IA está mirando lo que ella cree.
    resumen: str | None = None
    avisos: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo: str = ""


_PROMPT = (
    "Eres un delineante que revisa un plano de construcción español. NO midas "
    "nada y NO devuelvas coordenadas: no te las pido y las estimarías mal.\n\n"
    "Lee el plano y devuelve solo lo que esté ESCRITO en él:\n"
    "1. La escala de dibujo del cajetín o de debajo del título: «E 1:50», "
    "«ESCALA 1/100», «1:50». Devuelve solo el denominador como número entero. "
    "Si hay varias escalas o ninguna clara, deja `escala_denominador` a null y "
    "dilo en `avisos` — es mejor que la persona lo mire que calibrar el plano "
    "entero con un número dudoso.\n"
    "2. Las cotas acotadas que veas escritas, con su valor pasado a metros: "
    "«10,00» en un plano en metros son 10; «1050» en un plano en milímetros "
    "son 1,05. Di en `donde` a qué elemento acota, con palabras («fachada "
    "sur», «ancho del salón»).\n"
    "3. En `resumen`, una línea sobre qué es este plano (planta, alzado, "
    "sección, detalle; de qué).\n\n"
    "Responde exclusivamente con este JSON, sin texto alrededor:\n"
    '{"escala_denominador": entero o null, "escala_texto": string o null, '
    '"cotas": [{"texto": string, "metros": número, "donde": string o null}], '
    '"resumen": string, "avisos": [string]}'
)


async def interpretar(session: AsyncSession, contenido: bytes, mime_type: str) -> Lectura:
    from app.modules.ia.credenciales import credenciales_gemini

    if len(contenido) > MAX_TAMANO_IA:
        raise LecturaFallida(
            f"El fichero pasa de {MAX_TAMANO_IA // (1024 * 1024)} MB y no se puede "
            "mandar a leer"
        )

    credenciales = await credenciales_gemini(session)
    if not credenciales.api_key:
        raise LecturaFallida(
            "Gemini no tiene clave configurada (Administración → Ajustes globales → IA)"
        )

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
        "generationConfig": {"responseMimeType": "application/json"},
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as cliente:
            respuesta = await cliente.post(
                f"{credenciales.base_url.rstrip('/')}/models/{credenciales.modelo}"
                ":generateContent",
                json=payload,
                headers={"X-goog-api-key": credenciales.api_key},
            )
    except httpx.HTTPError as exc:
        raise LecturaFallida(f"No se pudo contactar con Gemini: {exc}") from exc

    if respuesta.status_code >= 400:
        detalle = respuesta.text[:300]
        try:
            detalle = respuesta.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise LecturaFallida(f"Gemini rechazó la petición: {detalle}")

    cuerpo = respuesta.json()
    try:
        texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise LecturaFallida("Gemini ha devuelto una respuesta sin contenido") from exc

    lectura = _parsear(texto)
    uso = cuerpo.get("usageMetadata", {})
    lectura.modelo = credenciales.modelo
    lectura.tokens_entrada = int(uso.get("promptTokenCount", 0))
    lectura.tokens_salida = int(uso.get("candidatesTokenCount", 0))
    return lectura


def _parsear(texto: str) -> Lectura:
    """Del JSON del modelo a algo de lo que se pueda depender.

    Todo lo que no encaje se descarta y se dice en `avisos`, en vez de dejarlo
    pasar: aquí un dato malo no da un error, da una escala equivocada.
    """
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = limpio.split("```")[1].removeprefix("json").strip()
    try:
        bruto = json.loads(limpio)
    except json.JSONDecodeError as exc:
        raise LecturaFallida("Gemini no ha devuelto un JSON válido") from exc
    if not isinstance(bruto, dict):
        raise LecturaFallida("Gemini no ha devuelto un objeto")

    lectura = Lectura(
        escala_texto=_cadena(bruto.get("escala_texto")),
        resumen=_cadena(bruto.get("resumen")),
        avisos=[a for a in (bruto.get("avisos") or []) if isinstance(a, str)][:6],
    )

    denominador = bruto.get("escala_denominador")
    if isinstance(denominador, (int, float)) and denominador > 0:
        entero = int(denominador)
        if entero in ESCALAS_HABITUALES:
            lectura.escala_impresa = entero
        else:
            # No se acepta una escala rara: casi siempre es un «1:50» leído
            # como «1:5O» o una cifra del cajetín que no era la escala.
            lectura.avisos.append(
                f"Ha leído la escala 1:{entero}, que no es una de las que se usan. "
                "No me fío: calíbralo a mano."
            )

    for cruda in (bruto.get("cotas") or [])[:20]:
        if not isinstance(cruda, dict):
            continue
        try:
            metros = Decimal(str(cruda.get("metros")))
        except (InvalidOperation, TypeError):
            continue
        # Una cota de cero o de kilómetros no es una cota de un plano de obra.
        if not (Decimal("0.01") <= metros <= Decimal(1000)):
            continue
        lectura.cotas.append(
            CotaLeida(
                texto=_cadena(cruda.get("texto")) or str(metros),
                metros=metros,
                donde=_cadena(cruda.get("donde")),
            )
        )
    return lectura


def _cadena(valor: object) -> str | None:
    return valor.strip()[:250] if isinstance(valor, str) and valor.strip() else None


def escala_de_papel(denominador: int) -> Decimal:
    """Metros de obra por punto PDF, a partir de la escala impresa.

    Sin un solo píxel de por medio: un punto son 25,4/72 mm de papel, y a
    escala 1:N cada milímetro de papel son N milímetros de obra. Por eso esta
    calibración es exacta y la de pinchar una cota a ojo no lo es.
    """
    if denominador <= 0:
        raise LecturaFallida("La escala tiene que ser mayor que cero")
    return MM_POR_PUNTO * Decimal(denominador) / Decimal(1000)
