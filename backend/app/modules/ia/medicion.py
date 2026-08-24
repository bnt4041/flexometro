"""Orquesta la lectura de planos: llamada a Gemini + aplicación revisada al
estado de mediciones de una partida real.

Mismo principio que la sugerencia de patrones (Fase 9): `leer_plano` solo
persiste la propuesta cruda; `aplicar_lectura` —acción aparte, sobre la lista
ya revisada o editada en el frontend— es la única función que escribe líneas
de medición reales, reutilizando `presupuestos_service.crear_linea` para que
el recálculo de la partida sea exactamente el mismo que al añadir una línea a
mano.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.core import billing_service
from app.modules.ia import gemini
from app.modules.ia.models import LecturaPlano
from app.modules.ia.schemas import LineaMedicionSugeridaOut, LineaSugeridaLLM
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos.models_presupuesto import LineaMedicion, Partida
from app.modules.presupuestos.presupuesto_schemas import LineaMedicionCreate
from app.modules.presupuestos.presupuesto_service import crear_linea

MAX_TAMANO_BYTES = 15 * 1024 * 1024
MIME_PERMITIDOS = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


class PartidaInvalida(Exception):
    pass


class FicheroInvalido(Exception):
    pass


class LecturaNoEncontrada(Exception):
    pass


class LecturaYaAplicada(Exception):
    pass


async def _obtener_partida(session: AsyncSession, partida_id: uuid.UUID) -> Partida:
    org_id = require_organization_id()
    partida = await session.scalar(
        select(Partida).where(Partida.id == partida_id, Partida.organization_id == org_id)
    )
    if partida is None:
        raise PartidaInvalida("La partida no existe en esta organización")
    return partida


def _lineas_out(lineas: list[LineaSugeridaLLM]) -> list[LineaMedicionSugeridaOut]:
    return [
        LineaMedicionSugeridaOut(
            comentario=linea.comentario,
            uds=linea.uds,
            longitud=linea.longitud,
            anchura=linea.anchura,
            altura=linea.altura,
            parcial=calc.parcial_de(linea.uds, linea.longitud, linea.anchura, linea.altura),
        )
        for linea in lineas
    ]


def detalle(lectura: LecturaPlano) -> list[LineaMedicionSugeridaOut]:
    return _lineas_out([LineaSugeridaLLM(**linea) for linea in lectura.respuesta_cruda])


async def leer_plano(
    session: AsyncSession,
    partida_id: uuid.UUID,
    *,
    fichero_nombre: str,
    mime_type: str,
    contenido: bytes,
    principal: Principal,
) -> LecturaPlano:
    if mime_type not in MIME_PERMITIDOS:
        raise FicheroInvalido(
            f"Formato '{mime_type}' no admitido; sube PDF, PNG, JPEG o WebP"
        )
    if not contenido:
        raise FicheroInvalido("El fichero está vacío")
    if len(contenido) > MAX_TAMANO_BYTES:
        raise FicheroInvalido(
            f"El fichero supera el máximo de {MAX_TAMANO_BYTES // (1024 * 1024)} MB"
        )

    org_id = require_organization_id()
    partida = await _obtener_partida(session, partida_id)

    respuesta, uso = await gemini.leer_plano(
        session, contenido, mime_type, partida.resumen, partida.unidad
    )

    lectura = LecturaPlano(
        organization_id=org_id,
        partida_id=partida_id,
        fichero_nombre=fichero_nombre,
        modelo=uso.modelo,
        observaciones=respuesta.observaciones,
        respuesta_cruda=[linea.model_dump(mode="json") for linea in respuesta.lineas],
        aplicada_en=None,
        **datos_autoria(),
    )
    session.add(lectura)
    await session.flush()

    await billing_service.registrar_uso_ia(
        session,
        organization_id=org_id,
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
        proveedor="gemini",
        modelo=uso.modelo,
        tokens_entrada=uso.tokens_entrada,
        tokens_salida=uso.tokens_salida,
        referencia=str(lectura.id),
    )
    return lectura


async def obtener_lectura(
    session: AsyncSession, lectura_id: uuid.UUID
) -> LecturaPlano | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(LecturaPlano).where(
            LecturaPlano.id == lectura_id, LecturaPlano.organization_id == org_id
        )
    )


async def aplicar_lectura(
    session: AsyncSession, lectura_id: uuid.UUID, lineas: list[LineaSugeridaLLM]
) -> list[LineaMedicion]:
    lectura = await obtener_lectura(session, lectura_id)
    if lectura is None:
        raise LecturaNoEncontrada("La lectura no existe en esta organización")
    if lectura.aplicada_en is not None:
        raise LecturaYaAplicada("Esta lectura ya se aplicó a la partida")
    if lectura.partida_id is None:
        raise PartidaInvalida("La partida de esta lectura ya no existe")

    creadas: list[LineaMedicion] = []
    for orden, datos in enumerate(lineas):
        linea = await crear_linea(
            session,
            lectura.partida_id,
            LineaMedicionCreate(**datos.model_dump(), orden=orden),
        )
        if linea is None:
            raise PartidaInvalida("La partida de esta lectura ya no existe")
        creadas.append(linea)

    lectura.aplicada_en = datetime.now(UTC)
    await session.flush()
    return creadas


async def anadir_mediciones(
    session: AsyncSession, partida_id: uuid.UUID, lineas: list[LineaSugeridaLLM]
) -> list[LineaMedicion]:
    """Igual que `aplicar_lectura` pero sin una `LecturaPlano` de por medio —
    para las mediciones propuestas desde la conversación general de
    documentos (`documento.conversar`, herramienta
    `proponer_mediciones_partida`), que no pasa por `leer_plano` y por tanto
    no tiene una lectura que marcar como aplicada."""
    await _obtener_partida(session, partida_id)

    creadas: list[LineaMedicion] = []
    for orden, datos in enumerate(lineas):
        linea = await crear_linea(
            session, partida_id, LineaMedicionCreate(**datos.model_dump(), orden=orden)
        )
        if linea is None:
            raise PartidaInvalida("La partida ya no existe")
        creadas.append(linea)

    await session.flush()
    return creadas
