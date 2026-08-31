"""Las herramientas del copiloto.

Leer se hace al momento; escribir, nunca: las que empiezan por `proponer_`
devuelven una `Propuesta` que vuelve al navegador para que la persona la mire
y diga que sí. Lo que la aplica está en `ejecutores.py`, y vuelve a comprobar
el permiso desde cero — el camino de escritura del copiloto no es un atajo
por dentro, es la misma puerta que usa la pantalla.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select

from app.core.enums import Alcance
from app.modules.ia.copiloto import objetos
from app.modules.ia.copiloto.registro import (
    Contexto,
    Herramienta,
    HerramientaInvalida,
    Propuesta,
    registrar,
)

LIMITE_RESULTADOS = 15
LIMITE_MAXIMO = 50


def _presentable(valor: Any) -> Any:
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if hasattr(valor, "value"):  # enums
        return valor.value
    return valor


def _tipos_visibles(contexto: Contexto, accion: str = "ver") -> list[objetos.TipoObjeto]:
    return [t for t in objetos.catalogo() if contexto.puede(t.modulo, accion)]


def _tipo_o_error(contexto: Contexto, codigo: str, accion: str) -> objetos.TipoObjeto:
    tipo = objetos.obtener(codigo or "")
    if tipo is None:
        disponibles = ", ".join(t.codigo for t in _tipos_visibles(contexto, accion))
        raise HerramientaInvalida(f"«{codigo}» no es un tipo válido. Son: {disponibles}")
    if not contexto.puede(tipo.modulo, accion):
        # Se dice que no hay permiso, no que no exista: el modelo tiene que
        # poder contárselo a la persona en vez de inventarse una explicación.
        raise HerramientaInvalida(
            f"Esta persona no tiene permiso de «{accion}» sobre {tipo.etiqueta.lower()}"
        )
    return tipo


# ── Leer ────────────────────────────────────────────────────────────────


async def _buscar_objetos(contexto: Contexto, args: dict) -> Any:
    tipo = _tipo_o_error(contexto, args.get("tipo", ""), "ver")
    modelo = tipo.modelo()
    texto = (args.get("texto") or "").strip()
    limite = min(int(args.get("limite") or LIMITE_RESULTADOS), LIMITE_MAXIMO)

    consulta = select(modelo)
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(
            or_(*(getattr(modelo, c).ilike(patron) for c in tipo.busqueda))
        )

    # El alcance «solo los míos» se aplica AQUÍ, dentro de la consulta. Filtrar
    # después sería mentir en el recuento y, con un límite, esconder resultados
    # legítimos detrás de otros que la persona no puede ver.
    alcance = contexto.alcance_de(tipo.modulo, "ver")
    if alcance == Alcance.PROPIOS:
        if tipo.columna_autor is None:
            raise HerramientaInvalida(
                f"{tipo.etiqueta} no guarda quién lo creó, así que con el alcance "
                "«solo los míos» no se puede listar"
            )
        consulta = consulta.where(
            getattr(modelo, tipo.columna_autor) == contexto.principal.subject
        )

    filas = list(await contexto.session.scalars(consulta.limit(limite)))
    return {
        "tipo": tipo.codigo,
        "encontrados": len(filas),
        "hay_mas": len(filas) == limite,
        "resultados": [
            {c: _presentable(getattr(f, c, None)) for c in tipo.resumen}
            | {"ruta": tipo.ruta.format(id=f.id)}
            for f in filas
        ],
    }


def _esquema_buscar(contexto: Contexto) -> dict:
    tipos = _tipos_visibles(contexto)
    return {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": [t.codigo for t in tipos],
                "description": "\n".join(f"{t.codigo}: {t.etiqueta}" for t in tipos),
            },
            "texto": {
                "type": "string",
                "description": "Texto a buscar en código, nombre o razón social. "
                "Vacío devuelve los primeros.",
            },
            "limite": {"type": "integer", "description": f"Máximo {LIMITE_MAXIMO}."},
        },
        "required": ["tipo"],
    }


async def _ver_objeto(contexto: Contexto, args: dict) -> Any:
    tipo = _tipo_o_error(contexto, args.get("tipo", ""), "ver")
    try:
        objeto_id = uuid.UUID(str(args.get("id")))
    except (ValueError, TypeError) as exc:
        raise HerramientaInvalida("El id no tiene forma de identificador") from exc

    fila = await contexto.session.get(tipo.modelo(), objeto_id)
    # El RLS ya impide ver los de otra organización; esto cubre el alcance
    # «solo los míos», que es de aplicación y no de base de datos.
    if fila is None:
        raise HerramientaInvalida("No existe nada con ese id")
    if (
        contexto.alcance_de(tipo.modulo, "ver") == Alcance.PROPIOS
        and tipo.columna_autor
        and getattr(fila, tipo.columna_autor, None) != contexto.principal.subject
    ):
        raise HerramientaInvalida("Ese registro no es de esta persona")

    return {c: _presentable(getattr(fila, c, None)) for c in tipo.resumen} | {
        "ruta": tipo.ruta.format(id=fila.id)
    }


def _esquema_ver(contexto: Contexto) -> dict:
    return {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": [t.codigo for t in _tipos_visibles(contexto)],
            },
            "id": {"type": "string", "description": "El id que devolvió buscar_objetos."},
        },
        "required": ["tipo", "id"],
    }


async def _buscar_en_la_ayuda(contexto: Contexto, args: dict) -> Any:
    if "soporte" not in contexto.modulos_activos:
        raise HerramientaInvalida("Esta organización no tiene la wiki activada")
    from app.modules.soporte import service as soporte

    pregunta = (args.get("pregunta") or "").strip()
    if not pregunta:
        raise HerramientaInvalida("Hace falta una pregunta")
    trozos = await soporte.buscar(contexto.session, pregunta)
    if not trozos:
        # Que no encuentre nada es información, no un fallo: sin esto el
        # modelo se inventaría la respuesta creyendo que la wiki calla.
        return {
            "encontrado": False,
            "aviso": "La wiki no dice nada sobre esto. No te lo inventes: dilo y "
            "ofrece abrir un ticket.",
        }
    return {
        "encontrado": True,
        "fragmentos": [{"titulo": t["titulo"], "texto": t["texto"]} for t in trozos],
    }


def _esquema_ayuda(_contexto: Contexto) -> dict:
    return {
        "type": "object",
        "properties": {
            "pregunta": {
                "type": "string",
                "description": "La duda, con las palabras de la persona.",
            }
        },
        "required": ["pregunta"],
    }


async def _guia_de_la_interfaz(contexto: Contexto, _args: dict) -> Any:
    """Dónde está cada cosa. Sin esto, el copiloto manda a la gente a
    pantallas que no existen o que su cuenta no tiene activadas."""
    from app.core.modules import registry

    salida = []
    for spec in registry.all():
        if spec.code not in contexto.modulos_activos or not spec.nav:
            continue
        salida.append(
            {
                "modulo": spec.name,
                "descripcion": spec.description,
                "pantallas": [{"nombre": n.label, "ruta": n.path} for n in spec.nav],
            }
        )
    return {"estas_en": contexto.ruta_actual, "menu": salida}


async def _resumir_datos(contexto: Contexto, args: dict) -> Any:
    from app.modules.informes import fuentes as fuentes_informes
    from app.modules.informes import motor

    codigo = args.get("fuente") or ""
    fuente = fuentes_informes.obtener(codigo)
    if fuente is None or not contexto.puede(fuente.modulo, "ver"):
        disponibles = ", ".join(f.codigo for f in _fuentes_visibles(contexto))
        raise HerramientaInvalida(f"«{codigo}» no vale. Fuentes: {disponibles}")

    try:
        filas = await motor.ejecutar(
            contexto.session,
            fuente,
            dimensiones=list(args.get("dimensiones") or []),
            metricas=list(args.get("metricas") or []),
            filtros=args.get("filtros") or {},
            alcance=contexto.alcance_de(fuente.modulo, "ver"),
            subject=contexto.principal.subject,
            limite=LIMITE_MAXIMO,
        )
    except motor.InformeInvalido as exc:
        raise HerramientaInvalida(str(exc)) from exc
    return {"fuente": fuente.codigo, "filas": filas}


def _fuentes_visibles(contexto: Contexto) -> list:
    from app.modules.informes import fuentes as fuentes_informes

    return [f for f in fuentes_informes.catalogo() if contexto.puede(f.modulo, "ver")]


def _esquema_resumir(contexto: Contexto) -> dict:
    detalle = []
    for f in _fuentes_visibles(contexto):
        detalle.append(
            f"{f.codigo} ({f.etiqueta}) — agrupa por: "
            + ", ".join(d.nombre for d in f.dimensiones)
            + "; mide: "
            + ", ".join(m.nombre for m in f.metricas)
        )
    return {
        "type": "object",
        "properties": {
            "fuente": {
                "type": "string",
                "enum": [f.codigo for f in _fuentes_visibles(contexto)],
                "description": "\n".join(detalle),
            },
            "dimensiones": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Por qué agrupar. Vacío da el total de todo.",
            },
            "metricas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Qué contar o sumar. Hace falta al menos una.",
            },
            "filtros": {
                "type": "object",
                "description": "Dimensión → valor exacto por el que filtrar.",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["fuente", "metricas"],
    }


# ── Proponer (no escriben) ──────────────────────────────────────────────


async def _proponer_crear(contexto: Contexto, args: dict) -> Propuesta:
    from app.modules.importador import destinos

    codigo = args.get("tipo") or ""
    destino = destinos.obtener(codigo)
    if destino is None or not contexto.puede(destino.modulo, "crear"):
        disponibles = ", ".join(d.codigo for d in _destinos_visibles(contexto))
        raise HerramientaInvalida(f"«{codigo}» no vale. Se puede crear: {disponibles}")

    brutos = args.get("datos") or {}
    limpios: dict[str, Any] = {}
    for campo in destino.campos:
        if campo.nombre in brutos and brutos[campo.nombre] not in (None, ""):
            limpios[campo.nombre] = brutos[campo.nombre]
        elif campo.obligatorio:
            raise HerramientaInvalida(f"Falta «{campo.etiqueta}»")

    etiquetas = {c.nombre: c.etiqueta for c in destino.campos}
    principales = ", ".join(str(v) for v in list(limpios.values())[:2])
    return Propuesta(
        accion=f"crear:{destino.codigo}",
        resumen=f"Alta en {destino.etiqueta}: {principales}",
        datos=limpios,
        campos=[
            {"etiqueta": etiquetas.get(k, k), "valor": _legible(v)}
            for k, v in limpios.items()
        ],
    )


def _legible(valor: Any) -> str:
    """Para enseñárselo a una persona, no a un programador: un `True` en una
    tarjeta de confirmación se lee mal y hace dudar de si eso es un dato o un
    fallo."""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


def _destinos_visibles(contexto: Contexto) -> list:
    from app.modules.importador import destinos

    return [d for d in destinos.catalogo() if contexto.puede(d.modulo, "crear")]


def _esquema_crear(contexto: Contexto) -> dict:
    detalle = []
    for d in _destinos_visibles(contexto):
        campos = ", ".join(
            f"{c.nombre}{'*' if c.obligatorio else ''}" for c in d.campos
        )
        detalle.append(f"{d.codigo} ({d.etiqueta}) — campos: {campos}")
    return {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": [d.codigo for d in _destinos_visibles(contexto)],
                "description": "\n".join(detalle) + "\n(* = obligatorio)",
            },
            "datos": {"type": "object", "description": "Campo → valor."},
        },
        "required": ["tipo", "datos"],
    }


async def _proponer_abrir_ticket(contexto: Contexto, args: dict) -> Propuesta:
    if "soporte" not in contexto.modulos_activos:
        raise HerramientaInvalida("Esta organización no tiene los tickets activados")
    titulo = (args.get("titulo") or "").strip()
    descripcion = (args.get("descripcion") or "").strip()
    if not titulo or not descripcion:
        raise HerramientaInvalida("Un ticket necesita asunto y descripción")
    datos = {
        "titulo": titulo,
        "descripcion": descripcion,
        "tipo": args.get("tipo") or "incidencia",
        "prioridad": args.get("prioridad") or "normal",
        "ruta_origen": contexto.ruta_actual,
    }
    return Propuesta(
        accion="abrir_ticket",
        resumen=f"Abrir un ticket: «{titulo}»",
        datos=datos,
        campos=[
            {"etiqueta": "Asunto", "valor": titulo},
            {"etiqueta": "Descripción", "valor": descripcion},
            {"etiqueta": "Tipo", "valor": str(datos["tipo"])},
            {"etiqueta": "Prioridad", "valor": str(datos["prioridad"])},
        ],
    )


def _esquema_ticket(_contexto: Contexto) -> dict:
    return {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "El asunto, en una línea."},
            "descripcion": {
                "type": "string",
                "description": "Qué esperaba la persona, qué ha pasado y desde dónde. "
                "Redáctalo tú con lo que te haya contado.",
            },
            "tipo": {"type": "string", "enum": ["incidencia", "peticion", "duda"]},
            "prioridad": {
                "type": "string",
                "enum": ["baja", "normal", "alta", "urgente"],
            },
        },
        "required": ["titulo", "descripcion"],
    }


def registrar_catalogo_inicial() -> None:
    """Idempotente."""
    from app.modules.ia.copiloto.registro import obtener

    if obtener("buscar_objetos") is not None:
        return
    objetos.registrar_catalogo_inicial()
    # Los catálogos de los que dependen `proponer_crear` y `resumir_datos`.
    # Se registran aquí y no se da por hecho que el arranque de la aplicación
    # ya lo hizo: si el orden cambiase, esas dos herramientas desaparecerían
    # sin un solo error, y un copiloto que calla porque no encuentra sus
    # catálogos parece un copiloto tonto, no uno roto. Son idempotentes.
    from app.modules.importador.destinos import registrar_catalogo_inicial as _destinos
    from app.modules.informes.fuentes import registrar_catalogo_inicial as _fuentes

    _destinos()
    _fuentes()

    registrar(
        Herramienta(
            nombre="buscar_objetos",
            descripcion=(
                "Busca obras, terceros, presupuestos, facturas, pedidos o albaranes "
                "de esta organización. Úsala siempre antes de responder con datos: "
                "no contestes de memoria."
            ),
            parametros=_esquema_buscar,
            modulo=None,
            accion=None,
            ejecutar=_buscar_objetos,
            disponible_si=lambda c: bool(_tipos_visibles(c)),
        )
    )
    registrar(
        Herramienta(
            nombre="ver_objeto",
            descripcion="Los datos de un objeto concreto por su id.",
            parametros=_esquema_ver,
            modulo=None,
            accion=None,
            ejecutar=_ver_objeto,
            disponible_si=lambda c: bool(_tipos_visibles(c)),
        )
    )
    registrar(
        Herramienta(
            nombre="buscar_en_la_ayuda",
            descripcion=(
                "Busca en la wiki de la organización cómo se hace algo. Úsala "
                "SIEMPRE para preguntas de «cómo se…» antes de responder."
            ),
            parametros=_esquema_ayuda,
            modulo=None,
            accion=None,
            ejecutar=_buscar_en_la_ayuda,
        )
    )
    registrar(
        Herramienta(
            nombre="guia_de_la_interfaz",
            descripcion=(
                "Qué pantallas tiene esta organización y en qué ruta está cada una. "
                "Úsala antes de decirle a nadie dónde pinchar."
            ),
            parametros=lambda _c: {"type": "object", "properties": {}},
            modulo=None,
            accion=None,
            ejecutar=_guia_de_la_interfaz,
        )
    )
    registrar(
        Herramienta(
            nombre="resumir_datos",
            descripcion=(
                "Agrupa y suma datos de la organización (facturación por cliente, "
                "obras por estado…). Para cifras y totales, esto en vez de contar "
                "a mano lo que devuelva buscar_objetos."
            ),
            parametros=_esquema_resumir,
            modulo=None,
            accion=None,
            ejecutar=_resumir_datos,
            disponible_si=lambda c: bool(_fuentes_visibles(c)),
        )
    )
    registrar(
        Herramienta(
            nombre="proponer_crear",
            descripcion=(
                "Propone crear un registro. NO lo crea: la persona tiene que "
                "confirmarlo después. Dilo así al anunciarlo."
            ),
            parametros=_esquema_crear,
            modulo=None,
            accion=None,
            ejecutar=_proponer_crear,
            escribe=True,
            disponible_si=lambda c: bool(_destinos_visibles(c)),
        )
    )
    registrar(
        Herramienta(
            nombre="proponer_abrir_ticket",
            descripcion=(
                "Propone abrir un ticket de soporte, cuando no sabes resolver algo "
                "o la persona reporta un fallo. Tampoco lo abre hasta que lo "
                "confirme."
            ),
            parametros=_esquema_ticket,
            modulo=None,
            accion=None,
            ejecutar=_proponer_abrir_ticket,
            escribe=True,
        )
    )
