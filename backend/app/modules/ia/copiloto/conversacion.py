"""El turno de conversación del copiloto.

Varias llamadas al modelo por turno: pide una herramienta, se le da el
resultado, vuelve a pensar. El tope de vueltas no es una optimización — sin
él, un modelo que se atasca encadena búsquedas hasta agotar la paciencia y la
factura. En la última vuelta se le retiran las herramientas para obligarle a
cerrar con texto.

Una sola propuesta por turno, a propósito: confirmar tres cosas de golpe con
un botón es no confirmar nada.
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.modules.ia import deepseek
from app.modules.ia.copiloto import herramientas as catalogo_herramientas
from app.modules.ia.copiloto.registro import (
    Contexto,
    HerramientaInvalida,
    Propuesta,
    contexto_de,
    disponibles,
    formato_openai,
    obtener,
)

logger = logging.getLogger(__name__)

MAX_VUELTAS = 5

#: Señales de que el modelo CREE haber propuesto algo. No se usan para
#: adivinar intenciones: solo para detectar el caso en que anuncia una
#: propuesta pero no ha llamado a la herramienta, y entonces a la persona no
#: le sale ningún botón. Pasa sobre todo cuando el hilo ya tiene texto suyo
#: con esa pinta y se imita a sí mismo en vez de usar la herramienta.
_PISTAS_PROPUESTA = (
    "confírmalo",
    "confirmalo",
    "¿lo confirmas",
    "lo confirmas",
    "te lo propongo",
    "te propongo",
    "queda pendiente de que",
    "¿lo creo",
)


def _anuncia_propuesta(texto: str | None) -> bool:
    bajo = (texto or "").lower()
    return any(p in bajo for p in _PISTAS_PROPUESTA)


@dataclass(frozen=True)
class Turno:
    respuesta: str
    propuesta: Propuesta | None
    modelo: str
    tokens_entrada: int
    tokens_salida: int


def _prompt(contexto: Contexto) -> str:
    return (
        "Eres el copiloto de Flexómetro, un ERP de construcción español. Ayudas "
        "a la persona que lo está usando: le explicas cómo se hace algo, le "
        "buscas sus datos, se los resumes y le propones crear cosas.\n\n"
        "Reglas que no se saltan:\n"
        "1. No inventes datos. Si necesitas una cifra, un código o un nombre, "
        "búscalo con una herramienta. Si no lo encuentras, dilo.\n"
        "2. Distingue las dos clases de pregunta y no las confundas:\n"
        "   - «qué/cuánto/cuáles tengo yo» habla de SUS datos: usa "
        "buscar_objetos o resumir_datos y CONTESTA CON LOS DATOS. Explicar "
        "dónde mirarlo en vez de mirarlo es no haber contestado.\n"
        "   - «cómo se hace X» es un procedimiento: busca en la ayuda. Si la "
        "wiki no lo cuenta, dilo claramente y ofrece abrir un ticket en vez "
        "de improvisar un procedimiento.\n"
        "3. Tú no creas ni modificas NADA. Para proponer un alta TIENES QUE "
        "llamar a la herramienta proponer_crear: describirla en texto no crea "
        "ninguna propuesta y a la persona no le sale ningún botón, así que no "
        "pasaría nada. Y al anunciarla, no digas «he creado», «he dado de "
        "alta» ni «ya está»: no ha pasado. Di «te lo propongo, confírmalo "
        "abajo».\n"
        "4. Si algo no aparece, puede ser que esta persona no tenga permiso — no "
        "que no exista. No afirmes que algo no existe si la herramienta te ha "
        "dicho que es cuestión de permisos.\n"
        "5. Responde en español, breve y al grano. Sin rodeos ni disculpas.\n"
        "   Texto llano: nada de markdown. Sin **, sin ##, sin tablas. Para "
        "enumerar, guiones al principio de línea.\n"
        "6. Los importes en euros con coma decimal.\n\n"
        f"La persona se llama {contexto.principal.username}. "
        + (f"Está en la pantalla {contexto.ruta_actual}." if contexto.ruta_actual else "")
    )


async def conversar(
    session: AsyncSession,
    principal: Principal,
    mensajes: list[dict],
    *,
    ruta_actual: str | None = None,
) -> Turno:
    catalogo_herramientas.registrar_catalogo_inicial()
    contexto = await contexto_de(session, principal)
    contexto.ruta_actual = ruta_actual

    historial: list[dict] = [{"role": "system", "content": _prompt(contexto)}]
    historial.extend(mensajes)

    tokens_entrada = tokens_salida = 0
    modelo = ""
    propuesta: Propuesta | None = None
    reconducido = False

    for vuelta in range(MAX_VUELTAS):
        # Última vuelta: sin herramientas, para que cierre en texto. Y en
        # cuanto hay una propuesta se retiran las de escritura, que si no
        # encadena una segunda antes de que nadie haya dicho que sí a la
        # primera.
        if vuelta == MAX_VUELTAS - 1:
            ofrecidas = []
        else:
            ofrecidas = disponibles(contexto, permitir_escritura=propuesta is None)

        contenido, llamadas, uso = await deepseek.chat_con_herramientas(
            session, historial, formato_openai(ofrecidas, contexto) if ofrecidas else []
        )
        tokens_entrada += uso.tokens_entrada
        tokens_salida += uso.tokens_salida
        modelo = uso.modelo

        if not llamadas:
            # Anunciar una propuesta sin haberla creado deja a la persona
            # leyendo «confírmalo abajo» sin nada que pulsar. Se le avisa una
            # sola vez y se le da otra vuelta; si vuelve a no hacerlo, se
            # devuelve su texto tal cual en vez de insistir.
            if (
                propuesta is None
                and not reconducido
                and any(h.escribe for h in ofrecidas)
                and _anuncia_propuesta(contenido)
            ):
                reconducido = True
                historial.append({"role": "assistant", "content": contenido})
                historial.append(
                    {
                        "role": "user",
                        "content": (
                            "Has descrito la propuesta pero no has llamado a la "
                            "herramienta, así que no me ha salido ningún botón para "
                            "confirmarla. Llámala ahora con esos mismos datos."
                        ),
                    }
                )
                continue
            return Turno(
                respuesta=contenido or "No he sabido responder a eso.",
                propuesta=propuesta,
                modelo=modelo,
                tokens_entrada=tokens_entrada,
                tokens_salida=tokens_salida,
            )

        historial.append({"role": "assistant", "content": contenido, "tool_calls": llamadas})

        for llamada in llamadas:
            nombre = llamada["function"]["name"]
            try:
                argumentos = json.loads(llamada["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                argumentos = {}

            herramienta = obtener(nombre)
            if herramienta is None or herramienta not in ofrecidas:
                resultado: object = {
                    "error": f"«{nombre}» no está disponible en esta conversación"
                }
            else:
                try:
                    salida = await herramienta.ejecutar(contexto, argumentos)
                    if herramienta.escribe:
                        # La propuesta no viaja al modelo: se guarda para
                        # devolverla al navegador. Al modelo solo se le dice
                        # que ya está planteada, para que la anuncie y no la
                        # repita.
                        propuesta = salida  # type: ignore[assignment]
                        resultado = {
                            "ok": True,
                            "pendiente_de_confirmacion": salida.resumen,  # type: ignore[union-attr]
                        }
                    else:
                        resultado = salida
                except HerramientaInvalida as exc:
                    # Vuelve al modelo, no al usuario: que rectifique dentro
                    # de la misma conversación.
                    resultado = {"error": str(exc)}
                except Exception:  # noqa: BLE001
                    logger.exception("Fallo en la herramienta %s del copiloto", nombre)
                    resultado = {"error": "Esa consulta ha fallado por dentro"}

            historial.append(
                {
                    "role": "tool",
                    "tool_call_id": llamada["id"],
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                }
            )

    return Turno(
        respuesta="Me he liado dando vueltas. Prueba a preguntármelo de otra forma.",
        propuesta=propuesta,
        modelo=modelo,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
    )
