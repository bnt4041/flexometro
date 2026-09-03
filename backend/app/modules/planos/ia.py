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
class ElementoLeido:
    """Algo que la IA ha reconocido EN LA IMAGEN y sitúa sobre ella.

    Las coordenadas van normalizadas (0-1 sobre el ancho y el alto de la
    hoja, con el origen arriba a la izquierda) porque el modelo no sabe en qué
    unidades está la hoja; convertirlas es una multiplicación.

    Y son aproximadas, a diferencia de todo lo demás de este módulo: salen de
    mirar píxeles. Por eso lo que se dibuja con esto nace marcado
    (`propuesto_ia`) y se revisa antes de contar como medición.
    """

    tipo: str
    etiqueta: str
    puntos: list[tuple[Decimal, Decimal]]


@dataclass
class Lectura:
    #: El denominador de la escala impresa: 50 para «1:50». `None` si el plano
    #: no la lleva escrita o no se ha leído con seguridad.
    escala_impresa: int | None = None
    escala_texto: str | None = None
    cotas: list[CotaLeida] = field(default_factory=list)
    #: Lo reconocido sobre la imagen, si se ha pedido dibujar.
    elementos: list[ElementoLeido] = field(default_factory=list)
    #: Lo que responde a lo que se le haya preguntado, en texto.
    respuesta: str | None = None
    #: Qué ha visto del plano, en una línea. Para que la persona sepa que la
    #: IA está mirando lo que ella cree.
    resumen: str | None = None
    avisos: list[str] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo: str = ""


#: Tope de lo que se acepta dibujar de una vez. Un plano de planta tiene una
#: docena de estancias y unas decenas de huecos; cien formas es el modelo
#: enredándose, y además llenaría la hoja de geometría que nadie va a revisar.
MAX_ELEMENTOS = 40
MAX_PUNTOS = 120

#: Lo único que se le deja dibujar. Coincide con lo que el plano sabe medir
#: (`TipoElemento`), para que lo que proponga sea una medición de verdad y no
#: un adorno.
TIPOS_DIBUJABLES = frozenset({"area", "longitud", "conteo"})

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

#: Lo que se le añade cuando además tiene que señalar sobre la imagen. Aquí sí
#: se le piden coordenadas —es la única forma de señalar algo en una foto— pero
#: con dos cortafuegos: van normalizadas (no en metros, así que no se pueden
#: confundir con una medición) y lo que salga de aquí nace marcado como
#: propuesta, para que se revise antes de contar como medido.
_PROMPT_DIBUJAR = (
    "\n\nADEMÁS, señala sobre la imagen lo que reconozcas, en `elementos`. "
    "Aquí sí necesito posiciones, porque es la única forma de marcar algo en "
    "una imagen, pero úsalas SOLO para señalar dónde está cada cosa: el valor "
    "en metros no lo pones tú, lo calcula el programa con la escala.\n"
    "- Coordenadas normalizadas de 0 a 1: x de izquierda a derecha, y de "
    "arriba abajo. [0,0] es la esquina superior izquierda de la hoja entera y "
    "[1,1] la inferior derecha.\n"
    "- `tipo`: «area» para una estancia o superficie (polígono con su "
    "contorno, 3 puntos o más); «longitud» para un muro, tabique o tramo de "
    "fachada (línea de 2 puntos o más); «conteo» para elementos repetidos "
    "—puertas, ventanas, arquetas, luminarias— con UN punto por cada uno, "
    "todos en el mismo elemento.\n"
    "- `etiqueta`: cómo se llama, en español y corto («Salón», «Tabique "
    "pasillo», «Puertas de paso»).\n"
    f"- Como mucho {MAX_ELEMENTOS} elementos y {MAX_PUNTOS} puntos en cada "
    "uno. Si el plano tiene más, quédate con lo importante y dilo en "
    "`avisos`.\n"
    "- Si no distingues bien el contorno de algo, NO lo inventes: déjalo "
    "fuera y dilo en `avisos`. Una forma torcida da una medición mala.\n"
    "Añade al JSON: \"elementos\": [{\"tipo\": \"area|longitud|conteo\", "
    '"etiqueta": string, "puntos": [[x, y], ...]}]'
)

_PROMPT_PETICION = (
    "\n\nLa persona te pide esto en concreto, y es lo que manda sobre todo lo "
    "anterior: «{peticion}». Céntrate en eso: señala solo lo que haga falta "
    "para responderle y explica lo que hayas hecho en `respuesta`, en una o "
    "dos frases. Si lo que te pide no se puede sacar de este plano, dilo en "
    "`respuesta` en vez de inventarlo."
)


def _prompt(peticion: str | None, dibujar: bool, hoja: int | None, hojas: int) -> str:
    texto = _PROMPT
    if hojas > 1 and hoja:
        # Sin esto, en un PDF de veinte láminas el modelo mezcla la escala de
        # una con las cotas de otra, y si además señala, señala sobre la
        # página equivocada.
        texto += (
            f"\n\nEste fichero tiene {hojas} páginas y ahora mismo se está "
            f"trabajando sobre la PÁGINA {hoja}. Mira solo esa: la escala, las "
            "cotas y lo que señales tienen que ser de ella."
        )
    if dibujar:
        texto += _PROMPT_DIBUJAR
    if peticion:
        texto += _PROMPT_PETICION.format(peticion=peticion.strip()[:500])
        texto += '\nAñade al JSON: "respuesta": string'
    return texto


async def interpretar(
    session: AsyncSession,
    contenido: bytes,
    mime_type: str,
    *,
    peticion: str | None = None,
    dibujar: bool = False,
    hoja: int | None = None,
    hojas: int = 1,
) -> Lectura:
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
                    {"text": _prompt(peticion, dibujar, hoja, hojas)},
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
        respuesta=_cadena(bruto.get("respuesta")),
        avisos=[a for a in (bruto.get("avisos") or []) if isinstance(a, str)][:6],
        elementos=_elementos(bruto.get("elementos")),
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


#: Puntos mínimos por tipo. Un área con dos puntos no es un área, y aceptarla
#: daría un elemento sin valor que ensucia la hoja.
_MINIMO_PUNTOS = {"area": 3, "longitud": 2, "conteo": 1}


def _elementos(bruto: object) -> list[ElementoLeido]:
    """Lo señalado sobre la imagen, saneado.

    Se descarta sin miramientos lo que no encaje: un punto fuera de la hoja o
    un polígono de dos vértices son el modelo equivocándose, y colarlo llenaría
    el plano de formas raras que alguien tendría que ir borrando a mano.
    """
    if not isinstance(bruto, list):
        return []
    elementos: list[ElementoLeido] = []
    for crudo in bruto[:MAX_ELEMENTOS]:
        if not isinstance(crudo, dict):
            continue
        tipo = str(crudo.get("tipo") or "").strip().lower()
        if tipo not in TIPOS_DIBUJABLES:
            continue
        puntos = _puntos(crudo.get("puntos"))
        if len(puntos) < _MINIMO_PUNTOS[tipo]:
            continue
        elementos.append(
            ElementoLeido(
                tipo=tipo,
                etiqueta=_cadena(crudo.get("etiqueta")) or "Reconocido por la IA",
                puntos=puntos,
            )
        )
    return elementos


def _puntos(bruto: object) -> list[tuple[Decimal, Decimal]]:
    if not isinstance(bruto, list):
        return []
    puntos: list[tuple[Decimal, Decimal]] = []
    for par in bruto[:MAX_PUNTOS]:
        if isinstance(par, dict):
            par = [par.get("x"), par.get("y")]
        if not isinstance(par, (list, tuple)) or len(par) != 2:
            continue
        try:
            x, y = Decimal(str(par[0])), Decimal(str(par[1]))
        except (InvalidOperation, TypeError):
            continue
        # Fuera de la hoja no hay nada que señalar. No se recorta al borde: un
        # punto en 1,4 no es un punto en el borde, es una forma mal situada.
        if not (Decimal(0) <= x <= Decimal(1) and Decimal(0) <= y <= Decimal(1)):
            continue
        puntos.append((x, y))
    return puntos


def escala_de_papel(denominador: int) -> Decimal:
    """Metros de obra por punto PDF, a partir de la escala impresa.

    Sin un solo píxel de por medio: un punto son 25,4/72 mm de papel, y a
    escala 1:N cada milímetro de papel son N milímetros de obra. Por eso esta
    calibración es exacta y la de pinchar una cota a ojo no lo es.
    """
    if denominador <= 0:
        raise LecturaFallida("La escala tiene que ser mayor que cero")
    return MM_POR_PUNTO * Decimal(denominador) / Decimal(1000)
