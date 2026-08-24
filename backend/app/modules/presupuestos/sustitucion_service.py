"""Buscador de sustitutos para «cambiar por banco de precios» (Fase 52).

Tres fuentes posibles para una PARTIDA: el banco de precios propio, partidas
de otros presupuestos de la cuenta, y líneas ya certificadas (el precio con
el que de verdad se cobró, no uno propuesto). Para un COMPONENTE del
descompuesto solo el banco tiene sentido — un componente es siempre un
`Concepto`, no algo que se certifique aparte.

La IA (`sugerir_ia`) solo ordena y explica unos pocos candidatos que ya
salieron de la búsqueda normal — nunca inventa uno nuevo ni aplica nada por
su cuenta, el usuario elige siempre desde la lista.
"""

import json
import logging
import re
import uuid

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.core.tenancy import require_organization_id
from app.core.visibilidad import organizaciones_visibles
from app.modules.ia.credenciales import credenciales_deepseek
from app.modules.presupuestos.models import Concepto, TipoConcepto
from app.modules.presupuestos.models_presupuesto import Partida, Presupuesto
from app.modules.presupuestos.presupuesto_schemas import SustitutoCandidatoOut

logger = logging.getLogger(__name__)

LIMITE_POR_FUENTE = 8

# Con menos de esto no cuenta como palabra significativa (fuera "de", "en",
# "con", "y"...) — evita que una palabra corta genérica meta ruido en el OR.
_LONGITUD_MINIMA_PALABRA = 4


def _condiciones_texto(texto: str, *columnas: ColumnElement) -> ColumnElement:
    """OR de ILIKE por cada palabra significativa de `texto`, sobre cada
    columna dada — no un ILIKE de la frase entera.

    La búsqueda a mano de un usuario suele ser un par de palabras, donde un
    ILIKE de la frase completa ya funciona bien; pero la sugerencia
    automática al abrir el buscador manda el RESUMEN ENTERO de la partida
    como semilla ("Regularización de paramentos y suelo con mortero de
    cemento"), y esa frase completa casi nunca aparece igual en el banco de
    precios ni en otra partida — habría que decir exactamente lo mismo con
    las mismas palabras en el mismo orden. Buscar por palabra suelta encaja
    con lo que realmente hay: "paramentos" o "mortero" sueltas sí aparecen
    en fichas relacionadas, aunque la frase entera no coincida en ningún
    sitio."""
    palabras = [p for p in re.split(r"\s+", texto.strip()) if len(p) >= _LONGITUD_MINIMA_PALABRA]
    if not palabras:
        palabras = [texto.strip()] if texto.strip() else [""]
    return or_(
        *[
            or_(*[columna.ilike(f"%{palabra}%") for columna in columnas])
            for palabra in palabras
        ]
    )


async def _candidatos_banco(session: AsyncSession, texto: str) -> list[SustitutoCandidatoOut]:
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)
    stmt = (
        select(Concepto)
        .where(
            Concepto.organization_id.in_(ids_visibles),
            Concepto.activo.is_(True),
            _condiciones_texto(texto, Concepto.resumen, Concepto.codigo),
        )
        .order_by(Concepto.tipo, Concepto.codigo)
        .limit(LIMITE_POR_FUENTE)
    )
    conceptos = (await session.execute(stmt)).scalars().all()
    return [
        SustitutoCandidatoOut(
            origen="banco",
            concepto_id=c.id,
            codigo=c.codigo,
            resumen=c.resumen,
            unidad=c.unidad,
            precio=c.precio,
            tiene_descompuesto=c.tipo != TipoConcepto.BASICO,
            origen_detalle="Banco de precios",
        )
        for c in conceptos
    ]


async def _candidatos_presupuestos(
    session: AsyncSession,
    org_id: uuid.UUID,
    texto: str,
    excluir_partida_id: uuid.UUID | None,
) -> list[SustitutoCandidatoOut]:
    condiciones = [
        Partida.organization_id == org_id,
        _condiciones_texto(texto, Partida.resumen, Partida.codigo),
    ]
    if excluir_partida_id is not None:
        condiciones.append(Partida.id != excluir_partida_id)
    stmt = (
        select(Partida, Presupuesto.nombre, Presupuesto.codigo)
        .join(Presupuesto, Presupuesto.id == Partida.presupuesto_id)
        .where(*condiciones)
        .order_by(Presupuesto.fecha.desc().nullslast())
        .limit(LIMITE_POR_FUENTE)
    )
    filas = (await session.execute(stmt)).all()
    return [
        SustitutoCandidatoOut(
            origen="presupuesto",
            partida_id=p.id,
            codigo=p.codigo,
            resumen=p.resumen,
            unidad=p.unidad,
            precio=p.precio,
            tiene_descompuesto=True,
            origen_detalle=f"Presupuesto {pres_codigo} · {pres_nombre}",
        )
        for p, pres_nombre, pres_codigo in filas
    ]


async def _candidatos_certificaciones(
    session: AsyncSession, org_id: uuid.UUID, texto: str
) -> list[SustitutoCandidatoOut]:
    # Import diferido: `facturacion` importa de `presupuestos` a nivel de
    # módulo, así que hacerlo al revés aquí arriba crearía un ciclo.
    from app.modules.facturacion.models import Certificacion, CertificacionLinea
    from app.modules.obras.models import Obra

    stmt = (
        select(CertificacionLinea, Certificacion.numero, Obra.nombre)
        .join(Certificacion, Certificacion.id == CertificacionLinea.certificacion_id)
        .join(Obra, Obra.id == Certificacion.obra_id)
        .where(
            CertificacionLinea.organization_id == org_id,
            _condiciones_texto(texto, CertificacionLinea.resumen, CertificacionLinea.codigo),
        )
        .order_by(Certificacion.fecha.desc())
        .limit(LIMITE_POR_FUENTE)
    )
    filas = (await session.execute(stmt)).all()
    return [
        SustitutoCandidatoOut(
            origen="certificacion",
            partida_id=linea.partida_id,
            codigo=linea.codigo,
            resumen=linea.resumen,
            unidad=linea.unidad,
            precio=linea.precio,
            tiene_descompuesto=True,
            origen_detalle=f"Certificación nº{numero} · {obra_nombre}",
        )
        for linea, numero, obra_nombre in filas
    ]


async def buscar_candidatos(
    session: AsyncSession,
    *,
    texto: str,
    modo: str,
    excluir_partida_id: uuid.UUID | None = None,
) -> list[SustitutoCandidatoOut]:
    org_id = require_organization_id()
    candidatos = list(await _candidatos_banco(session, texto))
    if modo == "partida":
        candidatos += await _candidatos_presupuestos(session, org_id, texto, excluir_partida_id)
        candidatos += await _candidatos_certificaciones(session, org_id, texto)
    return candidatos


class _SugerenciaIA(BaseModel):
    indice: int
    razon: str = Field(max_length=200)


class _RespuestaSugerenciasIA(BaseModel):
    sugerencias: list[_SugerenciaIA] = Field(default_factory=list)


_PROMPT_SUGERIR = (
    "Eres un asistente de presupuestación de construcción en España. Te doy "
    "una partida o un componente que el usuario quiere sustituir, y una "
    "lista numerada de candidatos posibles (del banco de precios propio, de "
    "partidas de presupuestos anteriores, o de líneas ya certificadas). "
    "Elige como mucho 3 candidatos, solo los que de verdad se parezcan por "
    "descripción y unidad — no rellenes hasta 3 si no encajan tantos. "
    "Ordénalos de mejor a peor y da una razón muy corta (media frase) para "
    "cada uno. No inventes candidatos que no estén en la lista: usa solo "
    "sus índices tal cual te los doy. Responde exclusivamente con un JSON "
    'con este esquema exacto, sin texto adicional: {"sugerencias": '
    '[{"indice": number, "razon": string}]}'
)


async def sugerir_ia(
    session: AsyncSession,
    *,
    resumen: str,
    unidad: str,
    candidatos: list[SustitutoCandidatoOut],
) -> list[SustitutoCandidatoOut]:
    """Reordena `candidatos` con los sugeridos por DeepSeek primero — nunca
    añade ninguno nuevo. Si DeepSeek no está configurado o falla, devuelve
    la lista tal cual en vez de romper la búsqueda: la sugerencia es un
    extra, no algo de lo que dependa poder buscar y elegir a mano."""
    if not candidatos:
        return candidatos
    credenciales = await credenciales_deepseek(session)
    if not credenciales.api_key:
        return candidatos

    lista = [
        {
            "indice": i,
            "origen": c.origen,
            "codigo": c.codigo,
            "resumen": c.resumen,
            "unidad": c.unidad,
            "precio": str(c.precio),
        }
        for i, c in enumerate(candidatos)
    ]
    payload = {
        "model": credenciales.modelo,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _PROMPT_SUGERIR},
            {
                "role": "user",
                "content": (
                    f"A sustituir: «{resumen}» (unidad: {unidad}).\n"
                    f"Candidatos:\n{json.dumps(lista, ensure_ascii=False)}"
                ),
            },
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as cliente:
            respuesta = await cliente.post(
                f"{credenciales.base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {credenciales.api_key}"},
            )
            respuesta.raise_for_status()
        contenido = respuesta.json()["choices"][0]["message"]["content"]
        sugerencias = _RespuestaSugerenciasIA.model_validate(json.loads(contenido)).sugerencias
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Fallo al pedir sugerencias de sustituto a DeepSeek: %s", exc)
        return candidatos

    usados: set[int] = set()
    destacados: list[SustitutoCandidatoOut] = []
    for s in sugerencias:
        if not (0 <= s.indice < len(candidatos)) or s.indice in usados:
            continue
        usados.add(s.indice)
        destacados.append(
            candidatos[s.indice].model_copy(update={"sugerido": True, "razon_sugerencia": s.razon})
        )
    resto = [c for i, c in enumerate(candidatos) if i not in usados]
    return destacados + resto
