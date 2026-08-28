"""Asistente conversacional de "Ayuda con IA" sobre un Pedido de CLIENTE
(Fase 4 del plan "Capítulos, partidas y mediciones en Pedidos y Facturas").

Calcado de `app.modules.ia.asistente` (el mismo asistente ya en producción
sobre `Presupuesto`), resolviendo contra `Pedido`/`PedidoCapitulo`/
`PedidoPartida` en vez de `Presupuesto`/`Capitulo`/`Partida`. Solo tiene
sentido en pedidos de cliente: un pedido a proveedor no tiene descompuesto
que montar (la partida es siempre alzada), así que `conversar()` comprueba
`Pedido.tipo == CLIENTE` antes de nada y, si no lo es, lanza
`pedido_service.DescomposicionNoDisponible` — el router la traduce a 409,
igual que ya hace con el resto de escritura de descomposición de
`pedido_router.py`.

De las 8 herramientas de `ia.asistente`, aquí solo tienen sentido 6:
`proponer_componentes_ficha` y `proponer_capitulos_banco` son específicas
del banco de precios como objeto propio (una "ficha" no es una partida de
pedido) y no se replican. `buscar_conceptos_banco`/`resolver_componentes` se
reutilizan tal cual, importadas de `ia.asistente` — son genéricas, no
dependen de `Presupuesto`.
"""

import json
import uuid

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.tenancy import require_organization_id
from app.modules.compras import pedido_service as service
from app.modules.compras.models import Pedido, PedidoCapitulo, PedidoPartida, TipoPedido
from app.modules.compras.pedido_schemas import ContextoAyudaPedido, ConversarAyudaPedido
from app.modules.core import billing_service
from app.modules.ia import deepseek
from app.modules.ia.asistente import ResultadoConversacion, buscar_conceptos_banco, resolver_componentes
from app.modules.ia.schemas import (
    CapituloPropuestoOut,
    LineaMedicionSugeridaOut,
    LineaSugeridaLLM,
    MensajeConversacionIn,
    PartidaConComponentesOut,
    PropuestaAccionOut,
)
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.terceros.models import Tercero

MAX_TURNOS_HERRAMIENTAS = 4
LIMITE_RESULTADOS = 10
# Listar TODAS las partidas de UN pedido (sin texto de búsqueda, acotado por
# pedido_id) es un caso ya bien delimitado — no la búsqueda abierta sobre
# toda la cuenta, que sí necesita un tope bajo. Ver el mismo razonamiento en
# `ia.asistente.LIMITE_RESULTADOS_PRESUPUESTO`.
LIMITE_RESULTADOS_PEDIDO = 200


# Compartido entre `proponer_crear_partida` (un array de esto) y
# `proponer_capitulos` — idéntico a `ia.asistente._ESQUEMA_COMPONENTE`.
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
            "name": "buscar_pedidos",
            "description": (
                "Busca pedidos de CLIENTE de esta cuenta por nombre de cliente "
                "y/o texto libre (código del pedido) — solo pedidos de cliente, "
                "porque son los únicos que pueden llevar partidas con "
                f"descompuesto que tenga sentido copiar aquí. Devuelve como "
                f"mucho {LIMITE_RESULTADOS}, los más recientes primero."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cliente": {"type": "string", "description": "Nombre (o parte) del cliente"},
                    "texto": {"type": "string", "description": "Texto sobre el código del pedido"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_partidas",
            "description": (
                "Busca partidas por código o descripción, en cualquier pedido de "
                "esta cuenta o dentro de un pedido concreto si se sabe su id. "
                f"Devuelve como mucho {LIMITE_RESULTADOS}. Para ver TODAS las "
                "partidas que ya tiene un pedido (para organizarlas en "
                "capítulos, por ejemplo) — no busques por una palabra suelta "
                "que puede no aparecer en ninguna descripción: omite `texto` y "
                f"da solo `pedido_id`, así devuelve hasta {LIMITE_RESULTADOS_PEDIDO}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Texto a buscar en código o descripción — omítelo para listarlas todas",
                    },
                    "pedido_id": {
                        "type": "string",
                        "description": "uuid de un pedido para limitar la búsqueda a él",
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
                "Propón copiar una partida ya encontrada al pedido en el que "
                "está trabajando el usuario ahora mismo. No copia nada "
                "todavía — solo dejas lista la propuesta para que la confirme."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "partida_id": {"type": "string", "description": "uuid de la partida a copiar"},
                    "descripcion": {
                        "type": "string",
                        "description": "Frase corta: qué partida y de qué pedido/cliente",
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
                "pedido actual, con los componentes de su descompuesto que "
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
                "todas las fases de obra de un pedido (demolición, "
                "albañilería, fontanería, electricidad, acabados...) en una sola "
                "llamada, no una por mensaje: el usuario confirma el plan entero "
                "de golpe, porque no hay forma de encadenar una propuesta con la "
                "siguiente sin que confirme la anterior primero. Si el usuario "
                "pide organizar todo el pedido en fases, pon aquí TODOS los "
                "capítulos que hagan falta en un único array `capitulos`, no "
                "llames a esta herramienta varias veces. Cada partida de cada "
                "capítulo puede ser de dos tipos: (a) una partida que YA EXISTE "
                "en el pedido y solo hay que mover aquí — dale `partida_id` "
                "(encuéntrala antes con `buscar_partidas`, dando el "
                "`pedido_id` y sin `texto` para verlas todas); o (b) una "
                "partida NUEVA — dale `resumen`, `unidad` y `componentes` con su "
                "descompuesto, igual que en `proponer_crear_partida` (busca los "
                "componentes del banco antes con `buscar_conceptos_banco`). "
                "Puedes mezclar ambos tipos en el mismo capítulo. Cuando el "
                "usuario pida organizar o reordenar un pedido que ya tiene "
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
]


def _prompt_sistema(contexto: ContextoAyudaPedido) -> str:
    return (
        "Eres un asistente de presupuestación de construcción en España, "
        "dentro de la ficha del pedido de cliente «"
        f"{contexto.pedido_codigo}» (id {contexto.pedido_id}). "
        "El elemento sobre el que se abrió esta conversación es: "
        f"{json.dumps({'tipo': contexto.tipo, 'codigo': contexto.codigo, 'resumen': contexto.resumen, 'unidad': contexto.unidad, 'precio': str(contexto.precio) if contexto.precio is not None else None}, ensure_ascii=False)}. "
        "Puedes buscar pedidos de cliente, sus partidas y conceptos del banco "
        "de precios de TODA la cuenta (no solo este pedido) con las "
        "herramientas que tienes — son de solo lectura, úsalas con libertad "
        "para encontrar lo que te pidan. Si el usuario pide copiar o traer "
        "algo de otro pedido, búscalo y termina llamando a "
        "`proponer_copiar_partida`. Si pide una partida que no existe en "
        "ningún sitio (una partida nueva, con sus componentes), busca cada "
        "componente con `buscar_conceptos_banco` para tener su id exacto y "
        "termina llamando a `proponer_crear_partida` — no inventes un "
        "`concepto_id`, si no lo encuentras dilo en vez de suponerlo. Si el "
        "usuario da un precio de palabra para algo que no está en el banco "
        "(\"el carpintero me cobra 120€ por puerta\", un material concreto, "
        "etc.), no hace falta que exista un concepto para eso: usa ese "
        "componente como personalizado (marca `personalizado: true` y "
        "rellena resumen/unidad/precio/naturaleza con lo que ha dicho el "
        "usuario) — se da de alta como concepto nuevo al confirmar, no es "
        "una limitación real. Si el usuario quiere organizar el pedido por "
        "fases de obra (\"un capítulo de demolición\", \"monta la fase de "
        "fontanería\", \"organízame esto en capítulos\", \"hazlo todo de una "
        "vez\"...), usa `proponer_capitulos` en vez de `proponer_crear_partida` "
        "— y pon TODOS los capítulos que hagan falta en la misma llamada (un "
        "array), no uno por mensaje: no hay forma de proponer un capítulo, "
        "que lo confirme, y encadenar el siguiente sin que el usuario tenga "
        "que pedirlo otra vez, así que si sabes que hacen falta 4 fases, "
        "propónlas las 4 juntas. Esto casi siempre significa MOVER partidas "
        "que el pedido YA TIENE, no inventarlas de nuevo: antes de nada, "
        "llama a `buscar_partidas` con el `pedido_id` de este pedido y SIN "
        "`texto` para verlas todas (una palabra suelta puede no aparecer en "
        "ninguna descripción y parecer, por error, que el pedido está "
        "vacío) — si ya hay partidas, agrúpalas por fase dando su "
        "`partida_id` en cada entrada, no montes partidas nuevas con datos "
        "inventados. Solo crea partidas nuevas (`resumen`/`unidad`/"
        "`componentes`, resueltos contra el banco o personalizados) si el "
        "usuario pide contenido que de verdad no existe todavía. En los "
        "cuatro casos: nunca digas que ya está copiada, creada, movida o "
        "dada de alta, porque no lo está — solo lo propones, y quien "
        "pregunta decide si confirma. Responde siempre en español, breve y "
        "directo. No inventes precios que nadie te haya dado: los del banco "
        "salen de una búsqueda, los personalizados de lo que diga el propio "
        "usuario en la conversación."
    )


async def _buscar_pedidos(
    session: AsyncSession, org_id: uuid.UUID, cliente: str | None, texto: str | None
) -> list[dict]:
    """Solo pedidos de CLIENTE: son los únicos que pueden llevar partidas con
    descompuesto que tenga sentido copiar aquí — un pedido a proveedor es
    siempre alzado, precio directo."""
    stmt = (
        select(Pedido, Tercero.razon_social)
        .join(Tercero, Tercero.id == Pedido.cliente_id)
        .where(Pedido.organization_id == org_id, Pedido.tipo == TipoPedido.CLIENTE)
    )
    if cliente:
        stmt = stmt.where(Tercero.razon_social.ilike(f"%{cliente}%"))
    if texto:
        stmt = stmt.where(Pedido.codigo.ilike(f"%{texto}%"))
    stmt = stmt.order_by(Pedido.fecha.desc()).limit(LIMITE_RESULTADOS)
    filas = (await session.execute(stmt)).all()
    return [
        {
            "id": str(p.id),
            "codigo": p.codigo,
            "cliente": razon_social,
            "fecha": p.fecha.isoformat() if p.fecha else None,
            "estado": str(p.estado),
        }
        for p, razon_social in filas
    ]


async def _buscar_partidas(
    session: AsyncSession, org_id: uuid.UUID, texto: str | None, pedido_id: str | None
) -> list[dict]:
    condiciones = [PedidoPartida.organization_id == org_id]
    if pedido_id:
        try:
            condiciones.append(PedidoPartida.pedido_id == uuid.UUID(pedido_id))
        except ValueError:
            return [{"error": "pedido_id no es un uuid válido"}]
    if texto:
        patron = f"%{texto}%"
        condiciones.append(or_(PedidoPartida.resumen.ilike(patron), PedidoPartida.codigo.ilike(patron)))
    stmt = (
        select(PedidoPartida, PedidoCapitulo.resumen, Pedido.codigo)
        .join(PedidoCapitulo, PedidoCapitulo.id == PedidoPartida.capitulo_id)
        .join(Pedido, Pedido.id == PedidoPartida.pedido_id)
        .where(*condiciones)
        .order_by(Pedido.fecha.desc())
        .limit(LIMITE_RESULTADOS_PEDIDO if (not texto and pedido_id) else LIMITE_RESULTADOS)
    )
    filas = (await session.execute(stmt)).all()
    return [
        {
            "id": str(p.id),
            "pedido_id": str(p.pedido_id),
            "pedido_codigo": pedido_codigo,
            "capitulo_id": str(p.capitulo_id),
            "capitulo": cap_resumen,
            "codigo": p.codigo,
            "resumen": p.resumen,
            "unidad": p.unidad,
            "precio": str(p.precio),
        }
        for p, cap_resumen, pedido_codigo in filas
    ]


async def resolver_partida_item(
    session: AsyncSession, org_id: uuid.UUID, bruto_partida: dict
) -> tuple[PartidaConComponentesOut | None, str | None]:
    """Una entrada de `partidas` dentro de un capítulo propuesto: movida
    (`partida_id`, ya existe) o nueva (`resumen`/`unidad`/`componentes`,
    resueltos contra el banco o personalizados) — usado por
    `proponer_capitulos` para cada partida de cada capítulo. Igual que
    `ia.asistente.resolver_partida_item`, pero contra `PedidoPartida`."""
    partida_id_bruto = bruto_partida.get("partida_id")
    if partida_id_bruto:
        partida_existente = None
        try:
            partida_existente = await session.get(PedidoPartida, uuid.UUID(partida_id_bruto))
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
    contexto: ContextoAyudaPedido,
    mensajes: list[MensajeConversacionIn],
    _principal: Principal,
) -> ResultadoConversacion:
    org_id = require_organization_id()
    pedido = await service.obtener_obj(session, contexto.pedido_id)
    if pedido is None or pedido.tipo != TipoPedido.CLIENTE:
        raise service.DescomposicionNoDisponible(
            "El asistente de IA solo está disponible en pedidos de cliente; "
            "este pedido es de proveedor y no tiene descompuesto que montar"
        )

    historial: list[dict] = [{"role": "system", "content": _prompt_sistema(contexto)}]
    historial.extend({"role": m.rol, "content": m.contenido} for m in mensajes)

    tokens_entrada = 0
    tokens_salida = 0
    modelo = ""

    for turno in range(MAX_TURNOS_HERRAMIENTAS):
        herramientas = _HERRAMIENTAS if turno < MAX_TURNOS_HERRAMIENTAS - 1 else []
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

        historial.append({"role": "assistant", "content": contenido, "tool_calls": tool_calls})

        propuesta: PropuestaAccionOut | None = None
        for tc in tool_calls:
            nombre = tc["function"]["name"]
            try:
                argumentos = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                argumentos = {}

            if nombre == "buscar_pedidos":
                resultado: object = await _buscar_pedidos(
                    session, org_id, argumentos.get("cliente"), argumentos.get("texto")
                )
            elif nombre == "buscar_partidas":
                resultado = await _buscar_partidas(
                    session, org_id, argumentos.get("texto"), argumentos.get("pedido_id")
                )
            elif nombre == "proponer_copiar_partida":
                partida_id = argumentos.get("partida_id")
                partida = None
                if partida_id:
                    try:
                        partida = await session.get(PedidoPartida, uuid.UUID(partida_id))
                    except ValueError:
                        partida = None
                if partida is None or partida.organization_id != org_id:
                    resultado = {"error": "Esa partida no existe o no es de esta cuenta"}
                else:
                    propuesta = PropuestaAccionOut(
                        tipo="copiar_partida",
                        partida_id=partida.id,
                        descripcion=argumentos.get("descripcion") or f"Copiar «{partida.resumen}»",
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
                    componentes, ids_no_encontrados = await resolver_componentes(session, org_id, brutos)
                    if not componentes:
                        resultado = {"error": "Ninguno de los componentes indicados es válido"}
                    else:
                        propuesta = PropuestaAccionOut(
                            tipo="crear_partida",
                            resumen=resumen_nuevo,
                            unidad=unidad_nueva,
                            componentes=componentes,
                            descripcion=argumentos.get("descripcion") or f"Crear «{resumen_nuevo}»",
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


async def ayuda_conversar(
    session: AsyncSession, datos: ConversarAyudaPedido, principal: Principal
) -> ResultadoConversacion:
    """Un turno de "Ayuda con IA" sobre un pedido de cliente — mismo patrón
    que `ia.service.ayuda_linea_conversar`: puede implicar varias llamadas a
    DeepSeek por turnos de herramientas, así que el uso se registra una sola
    vez, ya sumado, al final."""
    org_id = require_organization_id()
    resultado = await conversar(session, datos.contexto, datos.mensajes, principal)

    await billing_service.registrar_uso_ia(
        session,
        organization_id=org_id,
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
        proveedor="deepseek",
        modelo=resultado.modelo,
        tokens_entrada=resultado.tokens_entrada,
        tokens_salida=resultado.tokens_salida,
        referencia=None,
    )
    return resultado
