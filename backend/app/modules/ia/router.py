import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.ia import documento, estadisticas, medicion, service
from app.modules.ia.deepseek import DeepSeekError
from app.modules.ia.gemini import GeminiError
from app.modules.ia.models import LecturaPlano, SugerenciaPatron
from app.modules.ia.schemas import (
    AplicarLecturaPlano,
    ConversarAyudaLinea,
    CrearPlantillaDesdeSugerencia,
    EstadisticasOut,
    LecturaPlanoDetalle,
    LecturaPlanoOut,
    MensajeConversacionIn,
    RespuestaAyudaLinea,
    RespuestaDocumento,
    SolicitarSugerencia,
    SugerenciaDetalle,
    SugerenciaOut,
)
from app.modules.presupuestos.presupuesto_schemas import LineaMedicionOut, PresupuestoOut

guard = Depends(require_module("ia"))
router = APIRouter(prefix="/api/ia", tags=["ia"], dependencies=[guard])


def _detalle(sugerencia: SugerenciaPatron) -> SugerenciaDetalle:
    return SugerenciaDetalle(
        **SugerenciaOut.model_validate(sugerencia).model_dump(),
        capitulos=sugerencia.sugerencia,
    )


@router.get("/estadisticas", response_model=EstadisticasOut)
async def obtener_estadisticas(
    tipo_obra: str | None = None,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("ia", "ver")),
) -> EstadisticasOut:
    stats = await estadisticas.calcular_estadisticas(session, tipo_obra)
    return EstadisticasOut(
        generico=stats.generico,
        total_presupuestos=stats.total_presupuestos,
        capitulos=[{"resumen": c.resumen, "veces": c.veces} for c in stats.capitulos],
        partidas=[
            {
                "concepto_id": p.concepto_id,
                "codigo": p.codigo,
                "resumen": p.resumen,
                "unidad": p.unidad,
                "veces": p.veces,
            }
            for p in stats.partidas
        ],
    )


@router.get("/sugerencias", response_model=Page[SugerenciaOut])
async def listar_sugerencias(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("ia", "ver")),
) -> Page[SugerenciaOut]:
    items, total = await service.listar_sugerencias(
        session,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    return Page(
        items=[SugerenciaOut.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/sugerencias", response_model=SugerenciaDetalle, status_code=status.HTTP_201_CREATED
)
async def solicitar_sugerencia(
    datos: SolicitarSugerencia,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("ia", "editar")),
) -> SugerenciaDetalle:
    try:
        sugerencia = await service.solicitar_sugerencia(session, datos, principal)
    except DeepSeekError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    await session.commit()
    return _detalle(sugerencia)


async def _sugerencia_propia(
    session: AsyncSession, sugerencia_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    sugerencia = await service.obtener_sugerencia(session, sugerencia_id)
    if sugerencia is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sugerencia no encontrada"
        )
    verificar_propiedad(alcance, principal, sugerencia.creado_por_subject)
    return sugerencia


@router.get("/sugerencias/{sugerencia_id}", response_model=SugerenciaDetalle)
async def detalle_sugerencia(
    sugerencia_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("ia", "ver")),
) -> SugerenciaDetalle:
    sugerencia = await _sugerencia_propia(session, sugerencia_id, alcance, principal)
    return _detalle(sugerencia)


@router.post(
    "/sugerencias/{sugerencia_id}/plantilla",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_plantilla(
    sugerencia_id: uuid.UUID,
    datos: CrearPlantillaDesdeSugerencia,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("ia", "editar")),
) -> PresupuestoOut:
    await _sugerencia_propia(session, sugerencia_id, alcance, principal)
    try:
        plantilla = await service.crear_plantilla_desde_sugerencia(
            session, sugerencia_id, datos
        )
    except service.SugerenciaNoEncontrada as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except service.SugerenciaYaAceptada as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    await session.commit()
    return PresupuestoOut.model_validate(plantilla)


@router.post("/ayuda-linea/conversar", response_model=RespuestaAyudaLinea)
async def ayuda_linea_conversar(
    datos: ConversarAyudaLinea,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("ia", "editar")),
) -> RespuestaAyudaLinea:
    """Un turno de "Ayuda con IA" (Fase 1g): conversación libre sobre una
    partida o capítulo, con acceso de solo lectura a toda la cuenta (puede
    buscar en cualquier presupuesto o partida propios) y, si hace falta,
    termina en una propuesta de acción — nunca la ejecuta ella sola, eso lo
    hace el cliente al confirmarla, contra los endpoints de pegar ya
    existentes. Nada de esto se guarda en el servidor: cada turno manda el
    historial completo, como cualquier API de chat sin estado."""
    try:
        resultado = await service.ayuda_linea_conversar(session, datos, principal)
    except DeepSeekError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    # Sin escritura propia (la conversación no se guarda), pero sí queda el
    # registro de uso para facturación — se confirma para que no se pierda si
    # la petición siguiente reutiliza la conexión antes de que cierre `get_session`.
    await session.commit()
    return RespuestaAyudaLinea(respuesta=resultado.respuesta, propuesta=resultado.propuesta)


# --- Lectura de planos (Gemini) ---


def _detalle_lectura(lectura: LecturaPlano) -> LecturaPlanoDetalle:
    return LecturaPlanoDetalle(
        **LecturaPlanoOut.model_validate(lectura).model_dump(),
        lineas=medicion.detalle(lectura),
    )


@router.post(
    "/mediciones", response_model=LecturaPlanoDetalle, status_code=status.HTTP_201_CREATED
)
async def leer_plano(
    partida_id: uuid.UUID = Form(...),
    fichero: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("ia", "editar")),
) -> LecturaPlanoDetalle:
    contenido = await fichero.read()
    try:
        lectura = await medicion.leer_plano(
            session,
            partida_id,
            fichero_nombre=fichero.filename or "plano",
            mime_type=fichero.content_type or "application/octet-stream",
            contenido=contenido,
            principal=principal,
        )
    except (medicion.PartidaInvalida, medicion.FicheroInvalido) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except GeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    await session.commit()
    return _detalle_lectura(lectura)


async def _lectura_propia(
    session: AsyncSession, lectura_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    lectura = await medicion.obtener_lectura(session, lectura_id)
    if lectura is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lectura no encontrada"
        )
    verificar_propiedad(alcance, principal, lectura.creado_por_subject)
    return lectura


@router.get("/mediciones/{lectura_id}", response_model=LecturaPlanoDetalle)
async def detalle_lectura(
    lectura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("ia", "ver")),
) -> LecturaPlanoDetalle:
    lectura = await _lectura_propia(session, lectura_id, alcance, principal)
    return _detalle_lectura(lectura)


@router.post("/mediciones/{lectura_id}/aplicar", response_model=list[LineaMedicionOut])
async def aplicar_lectura(
    lectura_id: uuid.UUID,
    datos: AplicarLecturaPlano,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("ia", "editar")),
) -> list[LineaMedicionOut]:
    await _lectura_propia(session, lectura_id, alcance, principal)
    try:
        creadas = await medicion.aplicar_lectura(session, lectura_id, datos.lineas)
    except medicion.LecturaNoEncontrada as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except medicion.LecturaYaAplicada as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except medicion.PartidaInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await session.commit()
    return [LineaMedicionOut.model_validate(l) for l in creadas]


# --- Conversación sobre un documento arrastrado (Fase "Arrastrar al presupuesto") ---


_EXTENSIONES_EXCEL = {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@router.post("/documentos/conversar", response_model=RespuestaDocumento)
async def documento_conversar(
    fichero: UploadFile = File(...),
    # JSON en un campo de formulario, no un body Pydantic normal: FastAPI no
    # admite mezclar `File(...)` con un body JSON en la misma petición.
    mensajes: str = Form(...),
    # Cuando se sabe sobre qué presupuesto se abrió la conversación, la IA
    # puede además proponer un capítulo nuevo con lo que lea del documento
    # (Fase 39) — sin esto, se queda en solo lectura como antes.
    presupuesto_id: uuid.UUID | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("ia", "editar")),
) -> RespuestaDocumento:
    """Un turno de conversación libre sobre un documento (PDF, imagen o
    Excel) arrastrado a una fila del presupuesto: sin guardar nada en el
    servidor, cada turno manda el fichero entero más el historial de texto —
    el fichero en sí se guarda aparte, contra `/api/documentos`, cuando el
    usuario lo decida desde la pantalla."""
    try:
        lista = json.loads(mensajes)
        historial = [MensajeConversacionIn.model_validate(m) for m in lista]
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'mensajes' no es una lista de mensajes válida: {exc}",
        ) from exc

    contenido = await fichero.read()
    mime_type = fichero.content_type or "application/octet-stream"
    # El navegador a veces no sabe el tipo MIME correcto de un .xlsx y manda
    # algo genérico; la extensión es la señal fiable, igual que con el BC3.
    if mime_type not in documento.MIME_PERMITIDOS:
        for extension, mime_real in _EXTENSIONES_EXCEL.items():
            if (fichero.filename or "").lower().endswith(extension):
                mime_type = mime_real
                break
    try:
        respuesta, propuesta = await documento.conversar(
            session,
            contenido,
            mime_type,
            historial,
            principal,
            presupuesto_id=presupuesto_id,
        )
    except documento.DocumentoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except GeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    await session.commit()
    return RespuestaDocumento(respuesta=respuesta, propuesta=propuesta)
