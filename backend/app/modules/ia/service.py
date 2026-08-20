"""Orquesta la sugerencia de patrones: estadísticas propias + DeepSeek +
creación de la plantilla resultante.

Aceptar una sugerencia no es automático de principio a fin: el usuario revisa
y puede editar la propuesta en el frontend antes de confirmarla, y solo esa
confirmación explícita (`crear_plantilla_desde_sugerencia`) escribe algo en
el cuadro de precios o en presupuestos. Las partidas que la IA propone como
nuevas se crean como Concepto real (unitario, precio 0,00, origen_dato=IA):
así el catálogo crece con el tiempo, pero cualquiera que lo use después ve
claramente que está sin tarifar.
"""

import uuid
from dataclasses import asdict
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.enums import OrigenDato
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.core import billing_service
from app.modules.ia import asistente, deepseek
from app.modules.ia.estadisticas import Estadisticas, calcular_estadisticas
from app.modules.ia.models import SugerenciaPatron
from app.modules.ia.schemas import (
    CapituloSugeridoOut,
    ConversarAyudaLinea,
    CrearPlantillaDesdeSugerencia,
    PartidaSugeridaLLM,
    PartidaSugeridaOut,
    SolicitarSugerencia,
)
from app.modules.presupuestos import service as presupuestos_service
from app.modules.presupuestos.models import Concepto, TipoConcepto
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    EstadoPresupuesto,
    Partida,
    Presupuesto,
)
from app.modules.presupuestos.presupuesto_service import (
    siguiente_codigo as siguiente_codigo_presupuesto,
)
from app.modules.presupuestos.schemas import ConceptoCreate


class SugerenciaNoEncontrada(Exception):
    pass


class SugerenciaYaAceptada(Exception):
    pass


def _estadisticas_a_json(stats: Estadisticas) -> dict:
    bruto = asdict(stats)
    for partida in bruto["partidas"]:
        partida["concepto_id"] = str(partida["concepto_id"])
    return bruto


async def _resolver_partidas(
    session: AsyncSession, org_id: uuid.UUID, partidas: list[PartidaSugeridaLLM]
) -> list[PartidaSugeridaOut]:
    """Cruza lo que ha propuesto el modelo contra el cuadro de precios real.

    Nunca se confía en el resumen/unidad que el LLM repite de un código
    existente: si el código coincide con un concepto real de la organización,
    prevalecen los datos de ese concepto. Un código inventado por el modelo
    (alucinación) se trata igual que una propuesta nueva.
    """
    resueltas: list[PartidaSugeridaOut] = []
    for partida in partidas:
        concepto = None
        if partida.codigo_existente:
            concepto = await session.scalar(
                select(Concepto).where(
                    Concepto.organization_id == org_id,
                    Concepto.codigo == partida.codigo_existente,
                )
            )
        if concepto is not None:
            resueltas.append(
                PartidaSugeridaOut(
                    concepto_id=concepto.id,
                    codigo=concepto.codigo,
                    resumen=concepto.resumen,
                    unidad=concepto.unidad,
                    precio=concepto.precio,
                    es_nueva=False,
                )
            )
        else:
            resueltas.append(
                PartidaSugeridaOut(
                    concepto_id=None,
                    codigo=None,
                    resumen=partida.resumen,
                    unidad=partida.unidad,
                    precio=None,
                    es_nueva=True,
                )
            )
    return resueltas


async def solicitar_sugerencia(
    session: AsyncSession, datos: SolicitarSugerencia, principal: Principal
) -> SugerenciaPatron:
    org_id = require_organization_id()
    stats = await calcular_estadisticas(session, datos.tipo_obra)
    respuesta, uso = await deepseek.solicitar_sugerencia(
        session, datos.tipo_obra, datos.descripcion, stats
    )

    capitulos_resueltos: list[CapituloSugeridoOut] = []
    for capitulo in respuesta.capitulos:
        partidas = await _resolver_partidas(session, org_id, capitulo.partidas)
        capitulos_resueltos.append(
            CapituloSugeridoOut(resumen=capitulo.resumen, partidas=partidas)
        )

    sugerencia = SugerenciaPatron(
        organization_id=org_id,
        tipo_obra=datos.tipo_obra,
        descripcion=datos.descripcion,
        modelo=uso.modelo,
        estadisticas_enviadas=_estadisticas_a_json(stats),
        sugerencia=[c.model_dump(mode="json") for c in capitulos_resueltos],
        plantilla_id=None,
        **datos_autoria(),
    )
    session.add(sugerencia)
    await session.flush()

    await billing_service.registrar_uso_ia(
        session,
        organization_id=org_id,
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
        proveedor="deepseek",
        modelo=uso.modelo,
        tokens_entrada=uso.tokens_entrada,
        tokens_salida=uso.tokens_salida,
        referencia=str(sugerencia.id),
    )
    return sugerencia


async def ayuda_linea_conversar(
    session: AsyncSession,
    datos: ConversarAyudaLinea,
    principal: Principal,
) -> asistente.ResultadoConversacion:
    """Un turno de la conversación de "Ayuda con IA" (Fase 1g): puede
    implicar varias llamadas a DeepSeek por turnos de herramientas, así que
    el uso se registra una sola vez, ya sumado, al final — no una fila de
    facturación por cada búsqueda interna que haga el modelo."""
    org_id = require_organization_id()
    resultado = await asistente.conversar(session, datos.contexto, datos.mensajes, principal)

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


async def listar_sugerencias(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[SugerenciaPatron], int]:
    org_id = require_organization_id()
    base = select(SugerenciaPatron).where(SugerenciaPatron.organization_id == org_id)
    if creado_por_subject is not None:
        base = base.where(SugerenciaPatron.creado_por_subject == creado_por_subject)
    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    filas = await session.execute(
        base.order_by(SugerenciaPatron.created_at.desc()).limit(limit).offset(offset)
    )
    return list(filas.scalars()), int(total or 0)


async def obtener_sugerencia(
    session: AsyncSession, sugerencia_id: uuid.UUID
) -> SugerenciaPatron | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(SugerenciaPatron).where(
            SugerenciaPatron.id == sugerencia_id,
            SugerenciaPatron.organization_id == org_id,
        )
    )


async def crear_plantilla_desde_sugerencia(
    session: AsyncSession,
    sugerencia_id: uuid.UUID,
    datos: CrearPlantillaDesdeSugerencia,
) -> Presupuesto:
    org_id = require_organization_id()
    sugerencia = await obtener_sugerencia(session, sugerencia_id)
    if sugerencia is None:
        raise SugerenciaNoEncontrada("La sugerencia no existe en esta organización")
    if sugerencia.plantilla_id is not None:
        raise SugerenciaYaAceptada("Esta sugerencia ya generó una plantilla")

    codigo = datos.codigo or await siguiente_codigo_presupuesto(session)
    plantilla = Presupuesto(
        organization_id=org_id,
        codigo=codigo,
        nombre=datos.nombre,
        es_plantilla=True,
        tipo_obra=sugerencia.tipo_obra,
        estado=EstadoPresupuesto.BORRADOR,
        version=1,
        origen_dato=OrigenDato.IA,
        **datos_autoria(),
    )
    session.add(plantilla)
    await session.flush()

    for orden_capitulo, capitulo_in in enumerate(datos.capitulos):
        capitulo = Capitulo(
            organization_id=org_id,
            presupuesto_id=plantilla.id,
            parent_id=None,
            codigo=f"{orden_capitulo + 1:02d}",
            resumen=capitulo_in.resumen,
            orden=orden_capitulo,
        )
        session.add(capitulo)
        await session.flush()

        for orden_partida, partida_in in enumerate(capitulo_in.partidas):
            concepto = None
            if partida_in.concepto_id is not None:
                concepto = await session.scalar(
                    select(Concepto).where(
                        Concepto.id == partida_in.concepto_id,
                        Concepto.organization_id == org_id,
                    )
                )
            if concepto is None:
                # Propuesta nueva de la IA: entra en el cuadro de precios sin
                # tarifar, para que se revise antes de usarla en una obra real.
                concepto = await presupuestos_service.crear_concepto(
                    session,
                    ConceptoCreate(
                        tipo=TipoConcepto.UNITARIO,
                        resumen=partida_in.resumen,
                        unidad=partida_in.unidad,
                        precio=Decimal("0.00"),
                        origen_dato=OrigenDato.IA,
                    ),
                )

            session.add(
                Partida(
                    organization_id=org_id,
                    presupuesto_id=plantilla.id,
                    capitulo_id=capitulo.id,
                    concepto_id=concepto.id,
                    codigo=concepto.codigo,
                    resumen=concepto.resumen,
                    unidad=concepto.unidad,
                    precio=concepto.precio,
                    medicion=Decimal("0.000"),
                    importe=Decimal("0.00"),
                    orden=orden_partida,
                )
            )

    sugerencia.plantilla_id = plantilla.id
    await session.flush()
    return plantilla
