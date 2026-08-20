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

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.tenancy import require_organization_id
from app.modules.ia import deepseek
from app.modules.ia.schemas import (
    ComponentePropuestoOut,
    ContextoAyudaLinea,
    MensajeConversacionIn,
    PropuestaAccionOut,
)
from app.modules.presupuestos import service as banco_service
from app.modules.presupuestos.models import Concepto
from app.modules.presupuestos.models_presupuesto import Capitulo, Partida, Presupuesto
from app.modules.terceros.models import Tercero

MAX_TURNOS_HERRAMIENTAS = 4
LIMITE_RESULTADOS = 10


@dataclass(frozen=True)
class ResultadoConversacion:
    respuesta: str
    propuesta: PropuestaAccionOut | None
    modelo: str
    tokens_entrada: int
    tokens_salida: int


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
                f"como mucho {LIMITE_RESULTADOS}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string", "description": "Texto a buscar en código o descripción"},
                    "presupuesto_id": {
                        "type": "string",
                        "description": "uuid de un presupuesto para limitar la búsqueda a él",
                    },
                },
                "required": ["texto"],
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
                        "items": {
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
                                    "enum": [
                                        "mano_obra",
                                        "material",
                                        "maquinaria",
                                        "servicio",
                                        "otro",
                                    ],
                                    "description": "Tipo de recurso del componente personalizado (solo si personalizado es true)",
                                },
                            },
                            "required": ["rendimiento"],
                        },
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
]


def _prompt_sistema(contexto: ContextoAyudaLinea) -> str:
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
        "concepto nuevo al confirmar, no es una limitación real. En los tres "
        "casos: nunca digas que ya está copiada, creada o dada de alta, "
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
    session: AsyncSession, org_id: uuid.UUID, texto: str, presupuesto_id: str | None
) -> list[dict]:
    condiciones = [Partida.organization_id == org_id]
    if presupuesto_id:
        try:
            condiciones.append(Partida.presupuesto_id == uuid.UUID(presupuesto_id))
        except ValueError:
            return [{"error": "presupuesto_id no es un uuid válido"}]
    patron = f"%{texto}%"
    condiciones.append(or_(Partida.resumen.ilike(patron), Partida.codigo.ilike(patron)))
    stmt = (
        select(Partida, Capitulo.resumen, Presupuesto.nombre, Presupuesto.codigo)
        .join(Capitulo, Capitulo.id == Partida.capitulo_id)
        .join(Presupuesto, Presupuesto.id == Partida.presupuesto_id)
        .where(*condiciones)
        .order_by(Presupuesto.fecha.desc().nullslast())
        .limit(LIMITE_RESULTADOS)
    )
    filas = (await session.execute(stmt)).all()
    return [
        {
            "id": str(p.id),
            "presupuesto_id": str(p.presupuesto_id),
            "presupuesto_codigo": pres_codigo,
            "presupuesto_nombre": pres_nombre,
            "capitulo": cap_resumen,
            "codigo": p.codigo,
            "resumen": p.resumen,
            "unidad": p.unidad,
            "precio": str(p.precio),
        }
        for p, cap_resumen, pres_nombre, pres_codigo in filas
    ]


async def _buscar_conceptos_banco(session: AsyncSession, texto: str) -> list[dict]:
    conceptos, _total = await banco_service.listar_conceptos(
        session, q=texto, activo=True, limit=LIMITE_RESULTADOS
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
                texto = argumentos.get("texto")
                if not texto:
                    resultado = {"error": "Hace falta un texto para buscar"}
                else:
                    resultado = await _buscar_partidas(
                        session, org_id, texto, argumentos.get("presupuesto_id")
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
                    resultado = await _buscar_conceptos_banco(session, texto)
            elif nombre == "proponer_crear_partida":
                resumen_nuevo = argumentos.get("resumen")
                unidad_nueva = argumentos.get("unidad")
                brutos = argumentos.get("componentes") or []
                if not resumen_nuevo or not unidad_nueva or not brutos:
                    resultado = {
                        "error": "Faltan datos: hacen falta resumen, unidad y al menos un componente"
                    }
                else:
                    componentes: list[ComponentePropuestoOut] = []
                    ids_no_encontrados: list[str] = []
                    for bruto in brutos:
                        rendimiento = bruto.get("rendimiento")
                        if rendimiento is None:
                            ids_no_encontrados.append("(sin rendimiento)")
                            continue

                        if bruto.get("personalizado"):
                            resumen_comp = bruto.get("resumen")
                            unidad_comp = bruto.get("unidad")
                            precio_comp = bruto.get("precio")
                            if not resumen_comp or not unidad_comp or precio_comp is None:
                                ids_no_encontrados.append(
                                    f"personalizado incompleto: {bruto}"
                                )
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
                            ids_no_encontrados.append(str(concepto_id))
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
