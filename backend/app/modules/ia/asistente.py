"""Asistente conversacional de "Ayuda con IA" sobre una línea del presupuesto
(Fase 1g). A diferencia de `service.solicitar_sugerencia`/`medicion.leer_plano`
(un solo turno, respuesta estructurada que se procesa a mano), este es un
chat de varios turnos con function-calling: el modelo puede buscar en
cualquier presupuesto o partida de la cuenta (org-scoped, solo lectura) y, si
hace falta, terminar proponiendo una acción — nunca la ejecuta él: la
propuesta vuelve al frontend para que el usuario la confirme o la descarte,
y esa confirmación reutiliza los endpoints de copiar/pegar ya existentes
(Fase 1b/1c), no un camino de escritura nuevo.
"""

import json
import uuid
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.tenancy import require_organization_id
from app.modules.ia import deepseek
from app.modules.ia.schemas import (
    CapituloBancoPropuestoOut,
    CapituloPropuestoOut,
    ComponentePropuestoOut,
    ContextoAyudaLinea,
    FichaEnCapituloBancoOut,
    LineaMedicionSugeridaOut,
    LineaSugeridaLLM,
    MensajeConversacionIn,
    PartidaConComponentesOut,
    PropuestaAccionOut,
)
from app.modules.presupuestos import banco_service as capitulos_banco_service
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos import service as banco_service
from app.modules.presupuestos.models import Concepto
from app.modules.presupuestos.models_presupuesto import Capitulo, Partida, Presupuesto
from app.modules.terceros.models import Tercero

MAX_TURNOS_HERRAMIENTAS = 4
LIMITE_RESULTADOS = 10
# Listar TODAS las partidas de UN presupuesto (sin texto de búsqueda, acotado
# por presupuesto_id) es un caso ya bien delimitado — no la búsqueda abierta
# sobre toda la cuenta, que sí necesita un tope bajo.
LIMITE_RESULTADOS_PRESUPUESTO = 200
# El banco de precios puede tener miles de fichas (Fase 50): 10 por búsqueda
# de texto se queda corto para "organízalo todo", pero subir el límite
# general de golpe también engordaría las búsquedas de presupuestos/partidas,
# que no lo necesitan. Con esto sigue sin poder "verlas todas" a pulso de
# texto — para eso está `naturaleza` en `proponer_capitulos_banco`, que no
# depende de ningún límite de búsqueda porque no busca por texto.
LIMITE_RESULTADOS_BANCO = 40


@dataclass(frozen=True)
class ResultadoConversacion:
    respuesta: str
    propuesta: PropuestaAccionOut | None
    modelo: str
    tokens_entrada: int
    tokens_salida: int


# Compartido entre `proponer_crear_partida` (un array de esto) y
# `proponer_capitulos` (un array de capítulos, cada uno con un array de
# partidas, cada una con un array de esto) — mismo descompuesto, en los dos
# casos resuelto contra el banco o personalizado.
_ESQUEMA_COMPONENTE = {
    "type": "object",
    "properties": {
        "concepto_id": {
            "type": "string",
            "description": "uuid del concepto (de buscar_conceptos_banco) — omite esto si personalizado es true",
        },
        "rendimiento": {
            "type": "number",
            "description": "Cantidad de este componente por unidad de la partida",
        },
        "personalizado": {
            "type": "boolean",
            "description": (
                "true si este componente no está en el banco de precios y el "
                "usuario ha dado su propio precio (p. ej. \"el carpintero cobra "
                "120€ por puerta\"). En ese caso rellena resumen/unidad/precio/"
                "naturaleza en vez de concepto_id."
            ),
        },
        "resumen": {
            "type": "string",
            "description": "Descripción del componente personalizado (solo si personalizado es true)",
        },
        "unidad": {
            "type": "string",
            "description": "Unidad del componente personalizado: h, ud, m2... (solo si personalizado es true)",
        },
        "precio": {
            "type": "number",
            "description": "Precio unitario del componente personalizado, tal cual lo ha dado el usuario (solo si personalizado es true)",
        },
        "naturaleza": {
            "type": "string",
            "enum": ["mano_obra", "material", "maquinaria", "servicio", "otro"],
            "description": "Tipo de recurso del componente personalizado (solo si personalizado es true)",
        },
    },
    "required": ["rendimiento"],
}

_HERRAMIENTAS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_presupuestos",
            "description": (
                "Busca presupuestos de esta cuenta por nombre de cliente y/o "
                "texto libre (nombre, código o emplazamiento del presupuesto). "
                f"Devuelve como mucho {LIMITE_RESULTADOS}, los más recientes primero."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente": {"type": "string", "description": "Nombre (o parte) del cliente"},
                    "texto": {
                        "type": "string",
                        "description": "Texto sobre nombre, código o emplazamiento del presupuesto",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_partidas",
            "description": (
                "Busca partidas por código o descripción, en toda la cuenta o "
                "dentro de un presupuesto concreto si se sabe su id. Devuelve "
                f"como mucho {LIMITE_RESULTADOS}. Para ver TODAS las partidas que "
                "ya tiene un presupuesto (para organizarlas en capítulos, por "
                "ejemplo) — no busques por una palabra suelta que puede no "
                "aparecer en ninguna descripción: omite `texto` y da solo "
                f"`presupuesto_id`, así devuelve hasta {LIMITE_RESULTADOS_PRESUPUESTO}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Texto a buscar en código o descripción — omítelo para listarlas todas",
                    },
                    "presupuesto_id": {
                        "type": "string",
                        "description": "uuid de un presupuesto para limitar la búsqueda a él",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proponer_copiar_partida",
            "description": (
                "Propón copiar una partida ya encontrada al presupuesto en el "
                "que está trabajando el usuario ahora mismo. No copia nada "
                "todavía — solo dejas lista la propuesta para que la confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "partida_id": {"type": "string", "description": "uuid de la partida a copiar"},
                    "descripcion": {
                        "type": "string",
                        "description": "Frase corta: qué partida y de qué presupuesto/cliente",
                    },
                },
                "required": ["partida_id", "descripcion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_conceptos_banco",
            "description": (
                "Busca conceptos del banco de precios de esta cuenta (materiales, "
                "mano de obra, maquinaria...) por código o descripción — hace falta "
                "para saber el id exacto de un componente antes de proponer crear "
                f"una partida con él. Devuelve como mucho {LIMITE_RESULTADOS}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a buscar en código o descripción"},
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proponer_crear_partida",
            "description": (
                "Propón crear una partida NUEVA (no copiada de ningún sitio) en el "
                "presupuesto actual, con los componentes de su descompuesto que "
                "pida el usuario. Cada componente puede ser del banco de precios "
                "(búscalo antes con `buscar_conceptos_banco` para tener su id "
                "exacto) o personalizado, si el usuario ha dado un precio de "
                "palabra para algo que no está en el banco (un oficio, un "
                "material...) — en ese caso no hace falta concepto_id, se da de "
                "alta como concepto nuevo al confirmar. No crea nada todavía: "
                "solo deja lista la propuesta para que se confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "resumen": {"type": "string", "description": "Descripción de la partida nueva"},
                    "unidad": {
                        "type": "string",
                        "description": "Unidad de medida de la partida (ud, m2, m, h...)",
                    },
                    "componentes": {
                        "type": "array",
                        "description": "Componentes de su descompuesto",
                        "items": _ESQUEMA_COMPONENTE,
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Frase corta resumiendo la partida y sus componentes",
                    },
                },
                "required": ["resumen", "unidad", "componentes", "descripcion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proponer_capitulos",
            "description": (
                "Propón uno o VARIOS capítulos nuevos de una vez — por ejemplo, "
                "todas las fases de obra de un presupuesto (demolición, "
                "albañilería, fontanería, electricidad, acabados...) en una sola "
                "llamada, no una por mensaje: el usuario confirma el plan entero "
                "de golpe, porque no hay forma de encadenar una propuesta con la "
                "siguiente sin que confirme la anterior primero. Si el usuario "
                "pide organizar todo el presupuesto en fases, pon aquí TODOS los "
                "capítulos que hagan falta en un único array `capitulos`, no "
                "llames a esta herramienta varias veces. Cada partida de cada "
                "capítulo puede ser de dos tipos: (a) una partida que YA EXISTE "
                "en el presupuesto y solo hay que mover aquí — dale `partida_id` "
                "(encuéntrala antes con `buscar_partidas`, dando el "
                "`presupuesto_id` y sin `texto` para verlas todas); o (b) una "
                "partida NUEVA — dale `resumen`, `unidad` y `componentes` con su "
                "descompuesto, igual que en `proponer_crear_partida` (busca los "
                "componentes del banco antes con `buscar_conceptos_banco`). "
                "Puedes mezclar ambos tipos en el mismo capítulo. Cuando el "
                "usuario pida organizar o reordenar un presupuesto que ya tiene "
                "partidas, casi siempre quiere el tipo (a) — mover lo que ya "
                "existe, no inventarlo de nuevo. Los capítulos y sus partidas "
                "quedan en el orden en que los mandes, así que ordénalos tú de "
                "forma lógica (secuencia de ejecución). No mueve ni crea nada "
                "todavía: solo deja lista la propuesta para que se confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "capitulos": {
                        "type": "array",
                        "description": "Todos los capítulos a proponer, en el orden en que deben quedar",
                        "items": {
                            "type": "object",
                            "properties": {
                                "capitulo_resumen": {
                                    "type": "string",
                                    "description": "Nombre del capítulo (la fase de obra)",
                                },
                                "partidas": {
                                    "type": "array",
                                    "description": "Partidas del capítulo, en el orden en que deben quedar",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "partida_id": {
                                                "type": "string",
                                                "description": "uuid de una partida YA EXISTENTE (de buscar_partidas) para moverla aquí — si va esto, no hacen falta resumen/unidad/componentes",
                                            },
                                            "resumen": {
                                                "type": "string",
                                                "description": "Descripción de la partida nueva (solo si no hay partida_id)",
                                            },
                                            "unidad": {
                                                "type": "string",
                                                "description": "Unidad de medida de la partida nueva: ud, m2, m, h... (solo si no hay partida_id)",
                                            },
                                            "componentes": {
                                                "type": "array",
                                                "description": "Componentes del descompuesto de la partida nueva (solo si no hay partida_id)",
                                                "items": _ESQUEMA_COMPONENTE,
                                            },
                                            "texto": {
                                                "type": "string",
                                                "description": "Descripción ampliada de la partida nueva, si hace falta explicar de qué trata más allá del resumen (solo si no hay partida_id)",
                                            },
                                        },
                                    },
                                },
                            },
                            "required": ["capitulo_resumen", "partidas"],
                        },
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Frase corta resumiendo el plan: cuántos capítulos y qué llevan",
                    },
                },
                "required": ["capitulos", "descripcion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proponer_componentes_ficha",
            "description": (
                "Propón añadir uno o varios componentes al descompuesto de LA "
                "FICHA sobre la que se abrió esta conversación (no es una "
                "partida de presupuesto, es una ficha del banco de precios). "
                "Cada componente puede ser del banco (búscalo antes con "
                "`buscar_conceptos_banco` para tener su id exacto) o "
                "personalizado, si el usuario ha dado un precio de palabra "
                "para algo que no está en el banco — en ese caso no hace "
                "falta concepto_id, se da de alta como concepto nuevo al "
                "confirmar. No añade nada todavía: solo deja lista la "
                "propuesta para que se confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "componentes": {
                        "type": "array",
                        "description": "Componentes a añadir al descompuesto de esta ficha",
                        "items": _ESQUEMA_COMPONENTE,
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Frase corta resumiendo qué componentes se añaden y por qué",
                    },
                },
                "required": ["componentes", "descripcion"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proponer_capitulos_banco",
            "description": (
                "Propón organizar el BANCO DE PRECIOS en uno o VARIOS "
                "capítulos nuevos de una vez, moviendo a cada uno las fichas "
                "que ya existen. Cada capítulo se rellena de una de DOS "
                "formas — usa la que corresponda, no mezcles las dos en el "
                "mismo capítulo: (a) `naturaleza` — TODAS las fichas de ese "
                "tipo (mano_obra/material/maquinaria/servicio/otro/"
                "sin_clasificar), sin que tengas que buscarlas ni "
                "enumerarlas: el servidor las localiza todas y no depende "
                "de ningún límite de búsqueda, así que úsala siempre que el "
                "usuario pida organizar POR NATURALEZA o pida cubrir TODAS "
                "las fichas de un tipo; (b) `concepto_ids` — una lista "
                "concreta de fichas (de `buscar_conceptos_banco`, con su id "
                "exacto), para cualquier otro criterio (fase de obra, un "
                "tema concreto...) donde no hay un campo estructurado que "
                "lo resuelva y hace falta buscar por texto — en ese caso, "
                "si el banco es grande, dilo: puede que no hayas encontrado "
                "todas. Pon TODOS los capítulos que hagan falta en la misma "
                "llamada (un array), no uno por mensaje. A diferencia de una "
                "partida de presupuesto, una ficha del banco no se inventa "
                "de nuevo. No mueve nada todavía: solo deja lista la "
                "propuesta para que se confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "capitulos": {
                        "type": "array",
                        "description": "Todos los capítulos a proponer",
                        "items": {
                            "type": "object",
                            "properties": {
                                "capitulo_resumen": {
                                    "type": "string",
                                    "description": "Nombre del capítulo (la fase o la naturaleza)",
                                },
                                "naturaleza": {
                                    "type": "string",
                                    "enum": [
                                        "mano_obra",
                                        "material",
                                        "maquinaria",
                                        "servicio",
                                        "otro",
                                        "sin_clasificar",
                                    ],
                                    "description": "TODAS las fichas de esta naturaleza, resueltas por el servidor — omite concepto_ids si usas esto",
                                },
                                "concepto_ids": {
                                    "type": "array",
                                    "description": "ids de fichas concretas YA EXISTENTES a mover (de buscar_conceptos_banco) — omite si usas naturaleza",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["capitulo_resumen"],
                        },
                    },
                    "descripcion": {
                        "type": "string",
                        "description": "Frase corta resumiendo el plan: cuántos capítulos y qué llevan",
                    },
                },
                "required": ["capitulos", "descripcion"],
            },
        },
    },
]

# Qué herramientas tiene sentido ofrecer según el contexto: sobre una ficha
# del banco no hay presupuestos ni partidas que buscar o copiar, y sobre una
# línea de presupuesto no existe "el descompuesto de la ficha actual" (esa
# ficha es el banco, la línea de presupuesto es otra cosa). Ofrecer las que
# no aplican solo invitaría al modelo a intentar usarlas y fallar.
_HERRAMIENTAS_FICHA = (
    "buscar_conceptos_banco",
    "proponer_componentes_ficha",
    "proponer_capitulos_banco",
)
_HERRAMIENTAS_POR_TIPO = {
    "ficha": [h for h in _HERRAMIENTAS if h["function"]["name"] in _HERRAMIENTAS_FICHA],
    "capitulo": [h for h in _HERRAMIENTAS if h["function"]["name"] not in _HERRAMIENTAS_FICHA],
    "partida": [h for h in _HERRAMIENTAS if h["function"]["name"] not in _HERRAMIENTAS_FICHA],
}


def _prompt_sistema(contexto: ContextoAyudaLinea) -> str:
    if contexto.tipo == "ficha":
        return (
            "Eres un asistente de presupuestación de construcción en España, "
            "dentro del BANCO DE PRECIOS, sobre la ficha «"
            f"{contexto.resumen}» (id {contexto.concepto_id}, código "
            f"{contexto.codigo or 'sin asignar'}, unidad {contexto.unidad or '?'}). "
            "Puedes buscar conceptos del banco de precios de toda la cuenta "
            "con `buscar_conceptos_banco` — es de solo lectura, úsala con "
            "libertad. Si el usuario pide montar o completar el descompuesto "
            "de esta ficha (\"esto lleva tanto cemento y tanta arena\", "
            "\"añádele la mano de obra\"...), busca cada componente antes con "
            "`buscar_conceptos_banco` para tener su id exacto y termina "
            "llamando a `proponer_componentes_ficha` — no inventes un "
            "`concepto_id`, si no lo encuentras dilo en vez de suponerlo. Si "
            "el usuario da un precio de palabra para algo que no está en el "
            "banco, no hace falta que exista un concepto para eso: usa ese "
            "componente como personalizado (marca `personalizado: true` y "
            "rellena resumen/unidad/precio/naturaleza con lo que ha dicho el "
            "usuario) — se da de alta como concepto nuevo al confirmar. Si "
            "en vez de esto el usuario pide ORGANIZAR el banco de precios "
            "(\"crea capítulos por fases\", \"agrúpalo por naturaleza\", "
            "\"reordena esto\"...), eso no es un componente de esta ficha: "
            "termina llamando a `proponer_capitulos_banco` con TODOS los "
            "capítulos que hagan falta en la misma llamada. Si el usuario "
            "pide organizar POR NATURALEZA (mano de obra, material, "
            "maquinaria...) o pide cubrir TODAS las fichas de un tipo, usa "
            "el campo `naturaleza` de cada capítulo — el servidor localiza "
            "TODAS las fichas de esa naturaleza él solo, sin que tengas que "
            "buscarlas ni enumerarlas, así que esto SÍ cubre el banco "
            "entero por completo. Solo recurre a buscar fichas por texto "
            "con `buscar_conceptos_banco` (y dar `concepto_ids` en vez de "
            "`naturaleza`) cuando el criterio que pide el usuario NO sea la "
            "naturaleza (una fase de obra, un tema, una palabra concreta) — "
            "en ese caso, si el banco es grande, dilo: la búsqueda por "
            "texto tiene un límite y puede que no hayas encontrado todas. "
            "Nunca inventes un concepto_id, una ficha del banco no se crea "
            "de nuevo al organizar, solo se mueve. Nunca digas que ya se ha "
            "añadido o movido, porque no es así — solo lo propones, y quien "
            "pregunta decide si confirma. Responde siempre en español, "
            "breve y directo. No inventes precios que nadie te haya dado."
        )
    return (
        "Eres un asistente de presupuestación de construcción en España, "
        "dentro de la ficha del presupuesto «"
        f"{contexto.presupuesto_nombre}» (id {contexto.presupuesto_id}). "
        "La línea sobre la que se abrió esta conversación es: "
        f"{json.dumps({'tipo': contexto.tipo, 'codigo': contexto.codigo, 'resumen': contexto.resumen, 'unidad': contexto.unidad, 'precio': str(contexto.precio) if contexto.precio is not None else None}, ensure_ascii=False)}. "
        "Puedes buscar presupuestos, partidas y conceptos del banco de precios "
        "de TODA la cuenta (no solo este presupuesto) con las herramientas que "
        "tienes — son de solo lectura, úsalas con libertad para encontrar lo "
        "que te pidan. Si el usuario pide copiar o traer algo de otro "
        "presupuesto, búscalo y termina llamando a `proponer_copiar_partida`. "
        "Si pide una partida que no existe en ningún sitio (una partida "
        "nueva, con sus componentes), busca cada componente con "
        "`buscar_conceptos_banco` para tener su id exacto y termina llamando "
        "a `proponer_crear_partida` — no inventes un `concepto_id`, si no lo "
        "encuentras dilo en vez de suponerlo. Si el usuario da un precio de "
        "palabra para algo que no está en el banco (\"el carpintero me cobra "
        "120€ por puerta\", un material concreto, etc.), no hace falta que "
        "exista un concepto para eso: usa ese componente como personalizado "
        "(marca `personalizado: true` y rellena resumen/unidad/precio/"
        "naturaleza con lo que ha dicho el usuario) — se da de alta como "
        "concepto nuevo al confirmar, no es una limitación real. Si el "
        "usuario quiere organizar el presupuesto por fases de obra (\"un "
        "capítulo de demolición\", \"monta la fase de fontanería\", "
        "\"organízame esto en capítulos\", \"hazlo todo de una vez\"...), usa "
        "`proponer_capitulos` en vez de `proponer_crear_partida` — y pon TODOS "
        "los capítulos que hagan falta en la misma llamada (un array), no uno "
        "por mensaje: no hay forma de proponer un capítulo, que lo confirme, y "
        "encadenar el siguiente sin que el usuario tenga que pedirlo otra vez, "
        "así que si sabes que hacen falta 4 fases, propónlas las 4 juntas. "
        "Esto casi siempre significa MOVER partidas que el presupuesto YA "
        "TIENE, no inventarlas de nuevo: antes de nada, llama a "
        "`buscar_partidas` con el `presupuesto_id` de este presupuesto y SIN "
        "`texto` para verlas todas (una palabra suelta puede no aparecer en "
        "ninguna descripción y parecer, por error, que el presupuesto está "
        "vacío) — si ya hay partidas, agrúpalas por fase dando su "
        "`partida_id` en cada entrada, no montes partidas nuevas con datos "
        "inventados. Solo crea partidas nuevas (`resumen`/`unidad`/"
        "`componentes`, resueltos contra el banco o personalizados) si el "
        "usuario pide contenido que de verdad no existe todavía. En los "
        "cuatro casos: nunca digas que ya está "
        "copiada, creada, movida o dada de alta, "
        "porque no lo está — solo lo propones, y quien pregunta decide si "
        "confirma. Responde siempre en español, breve y directo. No inventes "
        "precios que nadie te haya dado: los del banco salen de una búsqueda, "
        "los personalizados de lo que diga el propio usuario en la "
        "conversación."
    )


async def _buscar_presupuestos(
    session: AsyncSession, org_id: uuid.UUID, cliente: str | None, texto: str | None
) -> list[dict]:
    stmt = (
        select(Presupuesto, Tercero.razon_social)
        .outerjoin(Tercero, Tercero.id == Presupuesto.cliente_id)
        .where(Presupuesto.organization_id == org_id, Presupuesto.es_plantilla.is_(False))
    )
    if cliente:
        stmt = stmt.where(Tercero.razon_social.ilike(f"%{cliente}%"))
    if texto:
        patron = f"%{texto}%"
        stmt = stmt.where(
            or_(Presupuesto.nombre.ilike(patron), Presupuesto.codigo.ilike(patron))
        )
    stmt = stmt.order_by(Presupuesto.fecha.desc().nullslast()).limit(LIMITE_RESULTADOS)
    filas = (await session.execute(stmt)).all()
    return [
        {
            "id": str(p.id),
            "codigo": p.codigo,
            "nombre": p.nombre,
            "cliente": razon_social,
            "fecha": p.fecha.isoformat() if p.fecha else None,
            "version": p.version,
        }
        for p, razon_social in filas
    ]


async def _buscar_partidas(
    session: AsyncSession, org_id: uuid.UUID, texto: str | None, presupuesto_id: str | None
) -> list[dict]:
    condiciones = [Partida.organization_id == org_id]
    if presupuesto_id:
        try:
            condiciones.append(Partida.presupuesto_id == uuid.UUID(presupuesto_id))
        except ValueError:
            return [{"error": "presupuesto_id no es un uuid válido"}]
    if texto:
        patron = f"%{texto}%"
        condiciones.append(or_(Partida.resumen.ilike(patron), Partida.codigo.ilike(patron)))
    stmt = (
        select(Partida, Capitulo.resumen, Presupuesto.nombre, Presupuesto.codigo)
        .join(Capitulo, Capitulo.id == Partida.capitulo_id)
        .join(Presupuesto, Presupuesto.id == Partida.presupuesto_id)
        .where(*condiciones)
        .order_by(Presupuesto.fecha.desc().nullslast())
        # Sin texto de por medio pero acotado a UN presupuesto (listar TODO
        # lo que tiene, no buscar algo concreto): el límite genérico de la
        # cuenta entera se queda corto, un presupuesto normal ya tiene más
        # de 10 líneas. Sin texto Y sin presupuesto sigue siendo una
        # búsqueda abierta sobre toda la cuenta — se queda con el tope bajo.
        .limit(LIMITE_RESULTADOS_PRESUPUESTO if (not texto and presupuesto_id) else LIMITE_RESULTADOS)
    )
    filas = (await session.execute(stmt)).all()
    return [
        {
            "id": str(p.id),
            "presupuesto_id": str(p.presupuesto_id),
            "presupuesto_codigo": pres_codigo,
            "presupuesto_nombre": pres_nombre,
            "capitulo_id": str(p.capitulo_id),
            "capitulo": cap_resumen,
            "codigo": p.codigo,
            "resumen": p.resumen,
            "unidad": p.unidad,
            "precio": str(p.precio),
        }
        for p, cap_resumen, pres_nombre, pres_codigo in filas
    ]


async def buscar_conceptos_banco(session: AsyncSession, texto: str) -> list[dict]:
    conceptos, _total = await banco_service.listar_conceptos(
        session, q=texto, activo=True, limit=LIMITE_RESULTADOS_BANCO
    )
    return [
        {
            "id": str(c.id),
            "codigo": c.codigo,
            "resumen": c.resumen,
            "unidad": c.unidad,
            "precio": str(c.precio),
            "naturaleza": str(c.naturaleza),
        }
        for c in conceptos
    ]


async def resolver_componentes(
    session: AsyncSession, org_id: uuid.UUID, brutos: list[dict]
) -> tuple[list[ComponentePropuestoOut], list[str]]:
    """Componentes del descompuesto de una partida propuesta, del banco
    (resueltos contra `Concepto`) o personalizados — usado tanto por
    `proponer_crear_partida` (una partida suelta) como por
    `proponer_capitulos` (varias, una por partida de cada capítulo). Devuelve los
    componentes válidos y, aparte, qué no se pudo resolver (para que el
    modelo sepa qué le falló sin reventar toda la propuesta)."""
    componentes: list[ComponentePropuestoOut] = []
    no_encontrados: list[str] = []
    for bruto in brutos:
        rendimiento = bruto.get("rendimiento")
        if rendimiento is None:
            no_encontrados.append("(sin rendimiento)")
            continue

        if bruto.get("personalizado"):
            resumen_comp = bruto.get("resumen")
            unidad_comp = bruto.get("unidad")
            precio_comp = bruto.get("precio")
            if not resumen_comp or not unidad_comp or precio_comp is None:
                no_encontrados.append(f"personalizado incompleto: {bruto}")
                continue
            componentes.append(
                ComponentePropuestoOut(
                    resumen=resumen_comp,
                    unidad=unidad_comp,
                    rendimiento=rendimiento,
                    personalizado=True,
                    precio=precio_comp,
                    naturaleza=bruto.get("naturaleza") or "sin_clasificar",
                )
            )
            continue

        concepto_id = bruto.get("concepto_id")
        concepto = None
        if concepto_id:
            try:
                concepto = await session.get(Concepto, uuid.UUID(concepto_id))
            except ValueError:
                concepto = None
        if concepto is None or concepto.organization_id != org_id:
            no_encontrados.append(str(concepto_id))
            continue
        componentes.append(
            ComponentePropuestoOut(
                concepto_id=concepto.id,
                codigo=concepto.codigo,
                resumen=concepto.resumen,
                unidad=concepto.unidad,
                rendimiento=rendimiento,
            )
        )
    return componentes, no_encontrados


async def resolver_partida_item(
    session: AsyncSession, org_id: uuid.UUID, bruto_partida: dict
) -> tuple[PartidaConComponentesOut | None, str | None]:
    """Una entrada de `partidas` dentro de un capítulo propuesto: movida
    (`partida_id`, ya existe) o nueva (`resumen`/`unidad`/`componentes`,
    resueltos contra el banco o personalizados) — usado por
    `proponer_capitulos` para cada partida de cada capítulo."""
    partida_id_bruto = bruto_partida.get("partida_id")
    if partida_id_bruto:
        partida_existente = None
        try:
            partida_existente = await session.get(Partida, uuid.UUID(partida_id_bruto))
        except ValueError:
            pass
        if partida_existente is None or partida_existente.organization_id != org_id:
            return None, f"partida_id no existe en esta cuenta: {partida_id_bruto}"
        return (
            PartidaConComponentesOut(
                partida_id=partida_existente.id,
                resumen=partida_existente.resumen,
                unidad=partida_existente.unidad,
            ),
            None,
        )

    resumen_p = bruto_partida.get("resumen")
    unidad_p = bruto_partida.get("unidad")
    brutos_comp = bruto_partida.get("componentes") or []
    if not resumen_p or not unidad_p or not brutos_comp:
        return None, f"partida incompleta: {bruto_partida}"
    comp_ok, comp_no_encontrados = await resolver_componentes(session, org_id, brutos_comp)
    if not comp_ok:
        return None, f"«{resumen_p}»: ningún componente válido ({comp_no_encontrados})"

    mediciones_ok: list[LineaMedicionSugeridaOut] = []
    for bruto_linea in bruto_partida.get("mediciones") or []:
        try:
            linea = LineaSugeridaLLM.model_validate(bruto_linea)
        except ValidationError:
            continue
        mediciones_ok.append(
            LineaMedicionSugeridaOut(
                comentario=linea.comentario,
                uds=linea.uds,
                longitud=linea.longitud,
                anchura=linea.anchura,
                altura=linea.altura,
                parcial=calc.parcial_de(linea.uds, linea.longitud, linea.anchura, linea.altura),
            )
        )

    return (
        PartidaConComponentesOut(
            resumen=resumen_p,
            unidad=unidad_p,
            componentes=comp_ok,
            texto=bruto_partida.get("texto"),
            mediciones=mediciones_ok,
        ),
        None,
    )


async def conversar(
    session: AsyncSession,
    contexto: ContextoAyudaLinea,
    mensajes: list[MensajeConversacionIn],
    _principal: Principal,
) -> ResultadoConversacion:
    org_id = require_organization_id()
    historial: list[dict] = [{"role": "system", "content": _prompt_sistema(contexto)}]
    historial.extend({"role": m.rol, "content": m.contenido} for m in mensajes)

    tokens_entrada = 0
    tokens_salida = 0
    modelo = ""

    for turno in range(MAX_TURNOS_HERRAMIENTAS):
        # En el último turno permitido no se ofrecen herramientas: si para
        # entonces no ha contestado en texto, se le obliga a cerrar en vez de
        # dejarlo pedir una búsqueda más y devolver un turno vacío.
        herramientas = (
            _HERRAMIENTAS_POR_TIPO[contexto.tipo] if turno < MAX_TURNOS_HERRAMIENTAS - 1 else []
        )
        contenido, tool_calls, uso = await deepseek.chat_con_herramientas(
            session, historial, herramientas
        )
        tokens_entrada += uso.tokens_entrada
        tokens_salida += uso.tokens_salida
        modelo = uso.modelo

        if not tool_calls:
            return ResultadoConversacion(
                respuesta=contenido or "No he podido responder a eso.",
                propuesta=None,
                modelo=modelo,
                tokens_entrada=tokens_entrada,
                tokens_salida=tokens_salida,
            )

        historial.append(
            {"role": "assistant", "content": contenido, "tool_calls": tool_calls}
        )

        propuesta: PropuestaAccionOut | None = None
        for tc in tool_calls:
            nombre = tc["function"]["name"]
            try:
                argumentos = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                argumentos = {}

            if nombre == "buscar_presupuestos":
                resultado: object = await _buscar_presupuestos(
                    session, org_id, argumentos.get("cliente"), argumentos.get("texto")
                )
            elif nombre == "buscar_partidas":
                resultado = await _buscar_partidas(
                    session, org_id, argumentos.get("texto"), argumentos.get("presupuesto_id")
                )
            elif nombre == "proponer_copiar_partida":
                partida_id = argumentos.get("partida_id")
                partida = None
                if partida_id:
                    try:
                        partida = await session.get(Partida, uuid.UUID(partida_id))
                    except ValueError:
                        partida = None
                if partida is None or partida.organization_id != org_id:
                    resultado = {"error": "Esa partida no existe o no es de esta cuenta"}
                else:
                    propuesta = PropuestaAccionOut(
                        tipo="copiar_partida",
                        partida_id=partida.id,
                        descripcion=argumentos.get("descripcion")
                        or f"Copiar «{partida.resumen}»",
                    )
                    resultado = {"ok": True}
            elif nombre == "buscar_conceptos_banco":
                texto = argumentos.get("texto")
                if not texto:
                    resultado = {"error": "Hace falta un texto para buscar"}
                else:
                    resultado = await buscar_conceptos_banco(session, texto)
            elif nombre == "proponer_crear_partida":
                resumen_nuevo = argumentos.get("resumen")
                unidad_nueva = argumentos.get("unidad")
                brutos = argumentos.get("componentes") or []
                if not resumen_nuevo or not unidad_nueva or not brutos:
                    resultado = {
                        "error": "Faltan datos: hacen falta resumen, unidad y al menos un componente"
                    }
                else:
                    componentes, ids_no_encontrados = await resolver_componentes(
                        session, org_id, brutos
                    )
                    if not componentes:
                        resultado = {
                            "error": "Ninguno de los componentes indicados es válido"
                        }
                    else:
                        propuesta = PropuestaAccionOut(
                            tipo="crear_partida",
                            resumen=resumen_nuevo,
                            unidad=unidad_nueva,
                            componentes=componentes,
                            descripcion=argumentos.get("descripcion")
                            or f"Crear «{resumen_nuevo}»",
                        )
                        resultado = {
                            "ok": True,
                            "componentes_no_encontrados": ids_no_encontrados or None,
                        }
            elif nombre == "proponer_capitulos":
                brutos_capitulos = argumentos.get("capitulos") or []
                if not brutos_capitulos:
                    resultado = {"error": "Falta al menos un capítulo en 'capitulos'"}
                else:
                    capitulos_ok: list[CapituloPropuestoOut] = []
                    capitulos_con_error: list[str] = []
                    for bruto_capitulo in brutos_capitulos:
                        resumen_capitulo = bruto_capitulo.get("capitulo_resumen")
                        brutos_partidas = bruto_capitulo.get("partidas") or []
                        if not resumen_capitulo or not brutos_partidas:
                            capitulos_con_error.append(f"capítulo incompleto: {bruto_capitulo}")
                            continue
                        partidas_ok: list[PartidaConComponentesOut] = []
                        partidas_con_error: list[str] = []
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
                    if not capitulos_ok:
                        resultado = {
                            "error": "Ninguno de los capítulos indicados es válido",
                            "detalle": capitulos_con_error,
                        }
                    else:
                        total_partidas = sum(len(c.partidas) for c in capitulos_ok)
                        propuesta = PropuestaAccionOut(
                            tipo="crear_capitulos",
                            capitulos_propuestos=capitulos_ok,
                            descripcion=argumentos.get("descripcion")
                            or (
                                f"Crear {len(capitulos_ok)} capítulo"
                                f"{'s' if len(capitulos_ok) != 1 else ''} con "
                                f"{total_partidas} partidas en total"
                            ),
                        )
                        resultado = {
                            "ok": True,
                            "capitulos_con_error": capitulos_con_error or None,
                        }
            elif nombre == "proponer_componentes_ficha":
                brutos = argumentos.get("componentes") or []
                if not brutos:
                    resultado = {"error": "Falta al menos un componente en 'componentes'"}
                else:
                    componentes, ids_no_encontrados = await resolver_componentes(
                        session, org_id, brutos
                    )
                    if not componentes:
                        resultado = {"error": "Ninguno de los componentes indicados es válido"}
                    else:
                        propuesta = PropuestaAccionOut(
                            tipo="anadir_componentes_ficha",
                            componentes=componentes,
                            descripcion=argumentos.get("descripcion")
                            or f"Añadir {len(componentes)} componente(s) al descompuesto",
                        )
                        resultado = {
                            "ok": True,
                            "componentes_no_encontrados": ids_no_encontrados or None,
                        }
            elif nombre == "proponer_capitulos_banco":
                brutos_capitulos = argumentos.get("capitulos") or []
                if not brutos_capitulos:
                    resultado = {"error": "Falta al menos un capítulo en 'capitulos'"}
                else:
                    capitulos_banco_ok: list[CapituloBancoPropuestoOut] = []
                    capitulos_banco_con_error: list[str] = []
                    for bruto_capitulo in brutos_capitulos:
                        resumen_capitulo = bruto_capitulo.get("capitulo_resumen")
                        naturaleza_bruta = bruto_capitulo.get("naturaleza")
                        ids_brutos = bruto_capitulo.get("concepto_ids") or []
                        if not resumen_capitulo or (not naturaleza_bruta and not ids_brutos):
                            capitulos_banco_con_error.append(f"capítulo incompleto: {bruto_capitulo}")
                            continue

                        if naturaleza_bruta:
                            # Campo estructurado, no búsqueda: se resuelve
                            # entero contra la base, sin límite ni ids que
                            # enumerar — puede ser media plantilla del banco.
                            total, muestra = await capitulos_banco_service.previsualizar_por_naturaleza(
                                session, naturaleza_bruta
                            )
                            if total == 0:
                                capitulos_banco_con_error.append(
                                    f"«{resumen_capitulo}»: ninguna ficha de naturaleza {naturaleza_bruta}"
                                )
                                continue
                            capitulos_banco_ok.append(
                                CapituloBancoPropuestoOut(
                                    resumen=resumen_capitulo,
                                    fichas=[
                                        FichaEnCapituloBancoOut(
                                            concepto_id=c.id, codigo=c.codigo, resumen=c.resumen
                                        )
                                        for c in muestra
                                    ],
                                    naturaleza=naturaleza_bruta,
                                    total_fichas=total,
                                )
                            )
                            continue

                        fichas_ok: list[FichaEnCapituloBancoOut] = []
                        ids_no_encontrados: list[str] = []
                        for id_bruto in ids_brutos:
                            concepto = None
                            try:
                                concepto = await session.get(Concepto, uuid.UUID(id_bruto))
                            except ValueError:
                                pass
                            if concepto is None or concepto.organization_id != org_id:
                                ids_no_encontrados.append(str(id_bruto))
                                continue
                            fichas_ok.append(
                                FichaEnCapituloBancoOut(
                                    concepto_id=concepto.id,
                                    codigo=concepto.codigo,
                                    resumen=concepto.resumen,
                                )
                            )
                        if not fichas_ok:
                            capitulos_banco_con_error.append(
                                f"«{resumen_capitulo}»: ninguna ficha válida ({ids_no_encontrados})"
                            )
                            continue
                        capitulos_banco_ok.append(
                            CapituloBancoPropuestoOut(
                                resumen=resumen_capitulo, fichas=fichas_ok, total_fichas=len(fichas_ok)
                            )
                        )
                    if not capitulos_banco_ok:
                        resultado = {
                            "error": "Ninguno de los capítulos indicados es válido",
                            "detalle": capitulos_banco_con_error,
                        }
                    else:
                        total_fichas = sum(c.total_fichas for c in capitulos_banco_ok)
                        propuesta = PropuestaAccionOut(
                            tipo="organizar_capitulos_banco",
                            capitulos_banco_propuestos=capitulos_banco_ok,
                            descripcion=argumentos.get("descripcion")
                            or (
                                f"Crear {len(capitulos_banco_ok)} capítulo"
                                f"{'s' if len(capitulos_banco_ok) != 1 else ''} con "
                                f"{total_fichas} fichas en total"
                            ),
                        )
                        resultado = {
                            "ok": True,
                            "capitulos_con_error": capitulos_banco_con_error or None,
                        }
            else:
                resultado = {"error": f"Herramienta desconocida: {nombre}"}

            historial.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(resultado, ensure_ascii=False),
                }
            )

        if propuesta is not None:
            # Un turno más, sin herramientas, para que redacte la frase que
            # acompaña a la propuesta con lo que ya sabe — no hace falta que
            # busque nada más.
            contenido2, _, uso2 = await deepseek.chat_con_herramientas(session, historial, [])
            tokens_entrada += uso2.tokens_entrada
            tokens_salida += uso2.tokens_salida
            return ResultadoConversacion(
                respuesta=contenido2 or propuesta.descripcion,
                propuesta=propuesta,
                modelo=modelo,
                tokens_entrada=tokens_entrada,
                tokens_salida=tokens_salida,
            )

    return ResultadoConversacion(
        respuesta=(
            "No he terminado de resolverlo en los pasos que tengo permitidos. "
            "Prueba a preguntar de forma más concreta (por ejemplo, con el "
            "nombre exacto del cliente o de la partida)."
        ),
        propuesta=None,
        modelo=modelo,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
    )
