"""API del módulo PRL.

Dos routers muy distintos conviven aquí:

- `router`: el normal, tras `require_module("prl")` y `require_permiso`.
- `publico_router`: el espacio de firma SIN sesión, montado bajo
  `/api/publico/`. Se autoriza a sí mismo contra el token de la URL (ver
  `firma.acceso_firma`) y está declarado en `RUTAS_PUBLICAS_PERMITIDAS`
  (`app/core/middleware.py`), que `app.main` comprueba al arrancar.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.mensajeria import ofuscar_email
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.core.schemas import Page
from app.modules.prl import firma as firma_service
from app.modules.prl import service
from app.modules.prl.models import AmbitoPRL, EstadoFirma, EstadoFirmante
from app.modules.prl.schemas import (
    ETIQUETAS_PLANTILLA,
    CodigoEnviadoOut,
    DocumentoParaFirmar,
    DocumentoPRLCreate,
    DocumentoPRLOut,
    DocumentoPRLUpdate,
    EnvioFirmaOut,
    EtiquetaPlantilla,
    FichaPRLObra,
    FirmanteIn,
    FirmanteOut,
    FirmarIn,
    PersonalPRLOut,
    PlantillaDocumentoCreate,
    PlantillaDocumentoOut,
    PlantillaDocumentoUpdate,
    PosicionesFirmaIn,
    RechazarIn,
    RecursoCreate,
    RecursoResumen,
    RecursoUpdate,
    ResultadoFirmaOut,
    ResumenFirmante,
    ResumenVigencia,
    SolicitudFirmaCreate,
    SolicitudFirmaDetalle,
    SolicitudFirmaOut,
    SolicitudFirmaUpdate,
    TipoDocumentoPRLCreate,
    TipoDocumentoPRLOut,
    TipoDocumentoPRLUpdate,
)

# El espacio privado lleva la guarda de módulo; el público NO puede colgar de
# él (le aplicaría `require_module` y le pegaría el prefijo `/api/prl`), así
# que los dos se montan por separado en el `router` de abajo del todo.
logger = logging.getLogger(__name__)

guard = Depends(require_module("prl"))
router_privado = APIRouter(prefix="/api/prl", tags=["prl"], dependencies=[guard])
router = router_privado  # alias para no repetir el nombre en cada endpoint


def _no_encontrado(que: str = "El registro") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{que} no existe")


async def _con_firmantes(
    session: AsyncSession, solicitud, detalle: bool = False
):
    """Monta la salida de una solicitud con sus firmantes y los contadores.
    Se hace en un sitio para que el listado y la ficha no puedan discrepar."""
    firmantes = await firma_service.listar_firmantes(session, solicitud.id)
    modelo = SolicitudFirmaDetalle if detalle else SolicitudFirmaOut
    salida = modelo.model_validate(solicitud)
    salida.firmantes = [FirmanteOut.model_validate(f) for f in firmantes]
    salida.total_firmantes = len(firmantes)
    salida.firmas_hechas = sum(1 for f in firmantes if f.estado == EstadoFirmante.FIRMADA)
    return salida


# ── Recursos ────────────────────────────────────────────────────────────


@router.get("/recursos", response_model=Page[RecursoResumen])
async def listar_recursos(
    tipo: str | None = None,
    obra_id: uuid.UUID | None = None,
    solo_activos: bool = False,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> Page[RecursoResumen]:
    recursos, total = await service.listar_recursos(
        session,
        tipo=tipo,
        obra_id=obra_id,
        solo_activos=solo_activos,
        busqueda=q,
        limit=limit,
        offset=offset,
    )
    conteo = await service.contar_por_entidad(
        session, ambito=AmbitoPRL.RECURSO, entidad_ids=[r.id for r in recursos]
    )
    items = []
    for recurso in recursos:
        item = RecursoResumen.model_validate(recurso)
        caducados, por_caducar = conteo.get(recurso.id, (0, 0))
        item.documentos_caducados = caducados
        item.documentos_por_caducar = por_caducar
        items.append(item)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("/recursos", response_model=RecursoResumen, status_code=status.HTTP_201_CREATED)
async def crear_recurso(
    datos: RecursoCreate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "crear")),
) -> RecursoResumen:
    try:
        recurso = await service.crear_recurso(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except service.EntidadInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return RecursoResumen.model_validate(recurso)


@router.get("/recursos/{recurso_id}", response_model=RecursoResumen)
async def ver_recurso(
    recurso_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> RecursoResumen:
    recurso = await service.obtener_recurso(session, recurso_id)
    if recurso is None:
        raise _no_encontrado("El recurso")
    return RecursoResumen.model_validate(recurso)


@router.patch("/recursos/{recurso_id}", response_model=RecursoResumen)
async def actualizar_recurso(
    recurso_id: uuid.UUID,
    datos: RecursoUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> RecursoResumen:
    recurso = await service.obtener_recurso(session, recurso_id)
    if recurso is None:
        raise _no_encontrado("El recurso")
    try:
        recurso = await service.actualizar_recurso(session, recurso, datos)
    except service.EntidadInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return RecursoResumen.model_validate(recurso)


@router.delete("/recursos/{recurso_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_recurso(
    recurso_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "borrar")),
) -> None:
    recurso = await service.obtener_recurso(session, recurso_id)
    if recurso is None:
        raise _no_encontrado("El recurso")
    await session.delete(recurso)


# ── Catálogo de tipos ───────────────────────────────────────────────────


@router.get("/tipos", response_model=list[TipoDocumentoPRLOut])
async def listar_tipos(
    ambito: AmbitoPRL | None = None,
    solo_activos: bool = True,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> list[TipoDocumentoPRLOut]:
    tipos = await service.listar_tipos(session, ambito=ambito, solo_activos=solo_activos)
    return [TipoDocumentoPRLOut.model_validate(t) for t in tipos]


@router.post("/tipos", response_model=TipoDocumentoPRLOut, status_code=status.HTTP_201_CREATED)
async def crear_tipo(
    datos: TipoDocumentoPRLCreate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "crear")),
) -> TipoDocumentoPRLOut:
    tipo = await service.crear_tipo(session, datos)
    return TipoDocumentoPRLOut.model_validate(tipo)


@router.patch("/tipos/{tipo_id}", response_model=TipoDocumentoPRLOut)
async def actualizar_tipo(
    tipo_id: uuid.UUID,
    datos: TipoDocumentoPRLUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> TipoDocumentoPRLOut:
    tipo = await service.obtener_tipo(session, tipo_id)
    if tipo is None:
        raise _no_encontrado("El tipo de documento")
    tipo = await service.actualizar_tipo(session, tipo, datos)
    return TipoDocumentoPRLOut.model_validate(tipo)


@router.delete("/tipos/{tipo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_tipo(
    tipo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "borrar")),
) -> None:
    tipo = await service.obtener_tipo(session, tipo_id)
    if tipo is None:
        raise _no_encontrado("El tipo de documento")
    await session.delete(tipo)


# ── Documentos PRL ──────────────────────────────────────────────────────


@router.get("/documentos", response_model=list[DocumentoPRLOut])
async def listar_documentos(
    ambito: AmbitoPRL,
    entidad_id: uuid.UUID | None = None,
    solo_problemas: bool = False,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> list[DocumentoPRLOut]:
    return await service.listar_documentos(
        session, ambito=ambito, entidad_id=entidad_id, solo_problemas=solo_problemas
    )


@router.get("/documentos/resumen", response_model=ResumenVigencia)
async def resumen(
    ambito: AmbitoPRL,
    entidad_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> ResumenVigencia:
    return await service.resumen_vigencia(session, ambito=ambito, entidad_id=entidad_id)


@router.post("/documentos", response_model=DocumentoPRLOut, status_code=status.HTTP_201_CREATED)
async def crear_documento(
    datos: DocumentoPRLCreate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "crear")),
) -> DocumentoPRLOut:
    try:
        documento = await service.crear_documento(session, datos)
    except (service.TipoInvalido, service.EntidadInvalida) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return DocumentoPRLOut.model_validate(documento)


@router.patch("/documentos/{documento_id}", response_model=DocumentoPRLOut)
async def actualizar_documento(
    documento_id: uuid.UUID,
    datos: DocumentoPRLUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> DocumentoPRLOut:
    documento = await service.obtener_documento(session, documento_id)
    if documento is None:
        raise _no_encontrado("El documento")
    try:
        documento = await service.actualizar_documento(session, documento, datos)
    except service.TipoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return DocumentoPRLOut.model_validate(documento)


@router.delete("/documentos/{documento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_documento(
    documento_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "borrar")),
) -> None:
    documento = await service.obtener_documento(session, documento_id)
    if documento is None:
        raise _no_encontrado("El documento")
    await session.delete(documento)


# ── Personal (vista PRL) ────────────────────────────────────────────────


@router.get("/personal", response_model=list[PersonalPRLOut])
async def personal_prl(
    solo_activos: bool = True,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> list[PersonalPRLOut]:
    """Vigilancia de la plantilla: quién tiene qué caducado, de un vistazo."""
    from app.core.tenancy import require_organization_id
    from app.modules.obras.models import Personal

    org_id = require_organization_id()
    filtros = [Personal.organization_id == org_id]
    if solo_activos:
        filtros.append(Personal.activo.is_(True))
    personas = list(
        await session.scalars(select(Personal).where(*filtros).order_by(Personal.nombre))
    )
    conteo = await service.contar_por_entidad(
        session, ambito=AmbitoPRL.PERSONAL, entidad_ids=[p.id for p in personas]
    )
    salida = []
    for persona in personas:
        item = PersonalPRLOut.model_validate(persona)
        caducados, por_caducar = conteo.get(persona.id, (0, 0))
        item.documentos_caducados = caducados
        item.documentos_por_caducar = por_caducar
        salida.append(item)
    return salida


# ── Ficha PRL de una obra ───────────────────────────────────────────────


@router.get("/obras/{obra_id}", response_model=FichaPRLObra)
async def ficha_obra(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> FichaPRLObra:
    documentos = await service.listar_documentos(
        session, ambito=AmbitoPRL.OBRA, entidad_id=obra_id
    )
    resumen_obra = await service.resumen_vigencia(
        session, ambito=AmbitoPRL.OBRA, entidad_id=obra_id
    )
    solicitudes, _ = await service_listar_firmas(session, obra_id)
    avisos = await service.avisos_personal_de_obra(session, obra_id)
    return FichaPRLObra(
        documentos=documentos,
        resumen=resumen_obra,
        firmas=solicitudes,
        personal_con_avisos=avisos,
    )


async def service_listar_firmas(
    session: AsyncSession, obra_id: uuid.UUID | None
) -> tuple[list[SolicitudFirmaOut], int]:
    solicitudes, total = await firma_service.listar_solicitudes(session, obra_id=obra_id, limit=200)
    return [SolicitudFirmaOut.model_validate(s) for s in solicitudes], total


# ── Plantillas ──────────────────────────────────────────────────────────


@router.get("/plantillas/etiquetas", response_model=list[EtiquetaPlantilla])
async def etiquetas_plantilla(
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> list[EtiquetaPlantilla]:
    """Qué marcadores admite una plantilla. Se sirve desde el servidor y no se
    escribe a mano en el frontend para que no pueda quedar desfasado respecto
    a lo que `firma._rellenar` sustituye de verdad.

    Va ANTES de `/plantillas/{plantilla_id}` a propósito: si fuera después,
    FastAPI intentaría interpretar "etiquetas" como un UUID."""
    return [EtiquetaPlantilla(**e) for e in ETIQUETAS_PLANTILLA]


@router.get("/plantillas", response_model=list[PlantillaDocumentoOut])
async def listar_plantillas(
    ambito: AmbitoPRL | None = None,
    solo_activas: bool = False,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> list[PlantillaDocumentoOut]:
    plantillas = await service.listar_plantillas(session, ambito=ambito, solo_activas=solo_activas)
    return [PlantillaDocumentoOut.model_validate(p) for p in plantillas]


@router.post(
    "/plantillas", response_model=PlantillaDocumentoOut, status_code=status.HTTP_201_CREATED
)
async def crear_plantilla(
    datos: PlantillaDocumentoCreate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "crear")),
) -> PlantillaDocumentoOut:
    plantilla = await service.crear_plantilla(session, datos)
    return PlantillaDocumentoOut.model_validate(plantilla)


@router.get("/plantillas/{plantilla_id}", response_model=PlantillaDocumentoOut)
async def ver_plantilla(
    plantilla_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> PlantillaDocumentoOut:
    plantilla = await service.obtener_plantilla(session, plantilla_id)
    if plantilla is None:
        raise _no_encontrado("La plantilla")
    return PlantillaDocumentoOut.model_validate(plantilla)


@router.patch("/plantillas/{plantilla_id}", response_model=PlantillaDocumentoOut)
async def actualizar_plantilla(
    plantilla_id: uuid.UUID,
    datos: PlantillaDocumentoUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> PlantillaDocumentoOut:
    plantilla = await service.obtener_plantilla(session, plantilla_id)
    if plantilla is None:
        raise _no_encontrado("La plantilla")
    plantilla = await service.actualizar_plantilla(session, plantilla, datos)
    return PlantillaDocumentoOut.model_validate(plantilla)


@router.delete("/plantillas/{plantilla_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_plantilla(
    plantilla_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "borrar")),
) -> None:
    plantilla = await service.obtener_plantilla(session, plantilla_id)
    if plantilla is None:
        raise _no_encontrado("La plantilla")
    await session.delete(plantilla)


# ── Solicitudes de firma ────────────────────────────────────────────────


@router.get("/firmas", response_model=Page[SolicitudFirmaOut])
async def listar_firmas(
    obra_id: uuid.UUID | None = None,
    estado: EstadoFirma | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> Page[SolicitudFirmaOut]:
    solicitudes, total = await firma_service.listar_solicitudes(
        session, obra_id=obra_id, estado=estado, limit=limit, offset=offset
    )
    return Page(
        items=[await _con_firmantes(session, s) for s in solicitudes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/firmas", response_model=SolicitudFirmaDetalle, status_code=status.HTTP_201_CREATED)
async def crear_firma(
    datos: SolicitudFirmaCreate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "crear")),
) -> SolicitudFirmaDetalle:
    # Los contactos nuevos se crean ANTES: así el firmante ya nace con su
    # `contacto_id` y no hay que volver atrás a rellenarlo.
    await _guardar_contactos_nuevos(session, datos.firmantes, datos.tercero_id)
    try:
        solicitud = await firma_service.crear_solicitud(session, datos)
    except (firma_service.PlantillaInvalida, firma_service.DocumentoInvalido) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return await _con_firmantes(session, solicitud, detalle=True)


async def _guardar_contactos_nuevos(
    session: AsyncSession, firmantes: list, tercero_id_defecto=None
) -> None:
    """Da de alta en la agenda los firmantes marcados para guardar. Si ya
    existe un contacto con ese correo se reutiliza en vez de duplicarlo — al
    mandar el mismo acta a la misma persona dos veces, la agenda no debería
    llenarse de copias."""
    from app.core.tenancy import datos_autoria, require_organization_id
    from app.modules.terceros.models import Contacto

    org_id = require_organization_id()
    for entrada in firmantes:
        if entrada.contacto_id is not None or not entrada.guardar_como_contacto:
            continue
        existente = await session.scalar(
            select(Contacto.id).where(
                Contacto.organization_id == org_id,
                func.lower(Contacto.email) == entrada.email.lower().strip(),
            )
        )
        if existente is not None:
            entrada.contacto_id = existente
            continue
        # El nombre puede venir entero ("Ana Pérez López"): la primera palabra
        # va a `nombre` y el resto a `apellidos`, que es como lo guarda la
        # agenda.
        partes = entrada.nombre.strip().split(" ", 1)
        contacto = Contacto(
            organization_id=org_id,
            nombre=partes[0],
            apellidos=partes[1] if len(partes) > 1 else None,
            email=entrada.email.strip(),
            # El móvil, en `movil` y no en `telefono`: es el número al que se
            # le acaba de mandar un WhatsApp, no una centralita.
            movil=(entrada.telefono or "").strip() or None,
            tercero_id=entrada.tercero_id or tercero_id_defecto,
            **datos_autoria(),
        )
        session.add(contacto)
        await session.flush()
        entrada.contacto_id = contacto.id


@router.get("/firmas/{solicitud_id}", response_model=SolicitudFirmaDetalle)
async def ver_firma(
    solicitud_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "ver")),
) -> SolicitudFirmaDetalle:
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")
    return await _con_firmantes(session, solicitud, detalle=True)


@router.patch("/firmas/{solicitud_id}", response_model=SolicitudFirmaDetalle)
async def actualizar_firma(
    solicitud_id: uuid.UUID,
    datos: SolicitudFirmaUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> SolicitudFirmaDetalle:
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")
    try:
        solicitud = await firma_service.actualizar_solicitud(session, solicitud, datos)
    except firma_service.EstadoInvalido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return await _con_firmantes(session, solicitud, detalle=True)


@router.post(
    "/firmas/{solicitud_id}/firmantes",
    response_model=SolicitudFirmaDetalle,
    status_code=status.HTTP_201_CREATED,
)
async def anadir_firmante(
    solicitud_id: uuid.UUID,
    datos: FirmanteIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "crear")),
) -> SolicitudFirmaDetalle:
    """Suma un firmante a una solicitud ya enviada. No manda su enlace: eso se
    hace después con `/enviar?firmante_id=…`, igual que un reenvío, para que
    quien lo añade decida cuándo sale."""
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")
    try:
        await firma_service.anadir_firmante(session, solicitud, datos)
    except firma_service.EstadoInvalido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await _guardar_contactos_nuevos(session, [datos], solicitud.tercero_id)
    return await _con_firmantes(session, solicitud, detalle=True)


@router.delete("/firmas/{solicitud_id}/firmantes/{firmante_id}", response_model=SolicitudFirmaDetalle)
async def quitar_firmante(
    solicitud_id: uuid.UUID,
    firmante_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "borrar")),
) -> SolicitudFirmaDetalle:
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")
    try:
        await firma_service.quitar_firmante(session, solicitud, firmante_id)
    except firma_service.EstadoInvalido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return await _con_firmantes(session, solicitud, detalle=True)


@router.put("/firmas/{solicitud_id}/posiciones", response_model=SolicitudFirmaDetalle)
async def guardar_posiciones(
    solicitud_id: uuid.UUID,
    datos: PosicionesFirmaIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> SolicitudFirmaDetalle:
    """Dónde firma cada persona sobre el PDF, tal como lo dejó el emisor en el
    visor. Solo mientras el documento no esté cerrado: mover una firma ya
    hecha cambiaría lo que se acreditó."""
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")
    if solicitud.estado in (EstadoFirma.FIRMADA, EstadoFirma.RECHAZADA):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El documento ya está cerrado; no se pueden mover las firmas"
        )

    firmantes = {f.id: f for f in await firma_service.listar_firmantes(session, solicitud.id)}
    for entrada in datos.por_firmante:
        firmante = firmantes.get(entrada.firmante_id)
        if firmante is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Uno de los firmantes indicados no pertenece a este documento",
            )
        # Al que ya firmó no se le mueve el recuadro: su firma ya está puesta
        # donde estaba cuando la hizo.
        if firmante.estado == EstadoFirmante.FIRMADA:
            continue
        firmante.posiciones_firma = [p.model_dump() for p in entrada.posiciones]
    await session.flush()
    return await _con_firmantes(session, solicitud, detalle=True)


@router.post("/firmas/{solicitud_id}/enviar", response_model=list[EnvioFirmaOut])
async def enviar_firma(
    solicitud_id: uuid.UUID,
    request: Request,
    firmante_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> list[EnvioFirmaOut]:
    """Genera un enlace por firmante y manda su correo. Sin `firmante_id` va a
    todos los que aún no han respondido; con él, solo a ese (reenvío).

    Si el SMTP falla, el enlace se devuelve igual: es preferible que el
    usuario lo copie a mano que perder el trabajo por un problema de correo.
    """
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")

    firmantes = await firma_service.listar_firmantes(session, solicitud.id)
    if firmante_id is not None:
        firmantes = [f for f in firmantes if f.id == firmante_id]
        if not firmantes:
            raise _no_encontrado("El firmante")
    else:
        firmantes = [
            f
            for f in firmantes
            if f.estado in (EstadoFirmante.PENDIENTE, EstadoFirmante.VISTA)
        ]
    if not firmantes:
        raise HTTPException(status.HTTP_409_CONFLICT, "No queda ningún firmante pendiente")

    base = str(request.base_url).rstrip("/")
    salida: list[EnvioFirmaOut] = []
    for firmante in firmantes:
        try:
            token = await firma_service.preparar_envio(session, solicitud, firmante)
        except firma_service.EstadoInvalido as exc:
            salida.append(
                EnvioFirmaOut(
                    enviado=False, error=str(exc), enlace="", firmante_nombre=firmante.nombre
                )
            )
            continue
        enlace = f"{base}/firmar/{token}"
        try:
            canales, _ = await firma_service.enviar_enlace(session, solicitud, firmante, enlace)
            salida.append(
                EnvioFirmaOut(
                    enviado=True,
                    enlace=enlace,
                    canales=canales,
                    firmante_nombre=firmante.nombre,
                )
            )
        except Exception as exc:  # noqa: BLE001
            # Deliberadamente ancho: el enlace YA es válido. Que no salga por
            # ningún canal no puede hacer perder el trabajo — se copia a mano.
            logger.warning("Fallo al enviar la firma %s: %s", solicitud.codigo, exc)
            salida.append(
                EnvioFirmaOut(
                    enviado=False, error=str(exc), enlace=enlace, firmante_nombre=firmante.nombre
                )
            )
    return salida


@router.post("/firmas/{solicitud_id}/cancelar", response_model=SolicitudFirmaOut)
async def cancelar_firma(
    solicitud_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("prl", "editar")),
) -> SolicitudFirmaOut:
    solicitud = await firma_service.obtener_solicitud(session, solicitud_id)
    if solicitud is None:
        raise _no_encontrado("La solicitud de firma")
    if solicitud.estado == EstadoFirma.FIRMADA:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un documento ya firmado no se puede cancelar")
    solicitud.estado = EstadoFirma.CANCELADA
    await session.flush()
    return await _con_firmantes(session, solicitud)


# ── Espacio público de firma (sin sesión) ───────────────────────────────

publico_router = APIRouter(prefix="/api/publico/firma", tags=["publico"])


@publico_router.get("/{token}", response_model=DocumentoParaFirmar)
async def ver_para_firmar(
    contexto: firma_service.ContextoFirma = Depends(firma_service.acceso_firma),
    session: AsyncSession = Depends(get_session),
) -> DocumentoParaFirmar:
    await firma_service.marcar_vista(session, contexto)
    solicitud = contexto.solicitud
    firmantes = await firma_service.listar_firmantes(session, solicitud.id)
    return DocumentoParaFirmar(
        titulo=solicitud.titulo,
        origen=solicitud.origen,
        contenido_html=solicitud.contenido_html,
        destinatario_nombre=contexto.firmante.nombre,
        emisor=contexto.emisor,
        estado=solicitud.estado,
        mi_estado=contexto.firmante.estado,
        firmada_en=contexto.firmante.firmada_en,
        expira_en=solicitud.expira_en,
        posiciones_firma=contexto.firmante.posiciones_firma,
        # Sin correos: quien firma no tiene por qué ver la agenda del emisor.
        otros_firmantes=[
            ResumenFirmante(nombre=f.nombre, estado=f.estado, firmada_en=f.firmada_en)
            for f in firmantes
            if f.id != contexto.firmante.id
        ],
    )


@publico_router.get("/{token}/documento")
async def documento_para_firmar(
    contexto: firma_service.ContextoFirma = Depends(firma_service.acceso_firma),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """El PDF que hay que firmar, cuando el origen es un fichero.

    Sirve el binario por aquí y no con la URL normal de descarga porque esa
    exige sesión, y quien firma no tiene. El token de la URL ya acotó a qué
    solicitud pertenece: solo se entrega SU documento, nunca uno por id."""
    from app.core import storage
    from app.modules.documentos.models import Documento

    solicitud = contexto.solicitud
    if solicitud.documento_origen_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este documento no tiene fichero asociado")
    fila = (
        await session.execute(
            select(Documento.object_key, Documento.nombre_archivo, Documento.content_type).where(
                Documento.id == solicitud.documento_origen_id
            )
        )
    ).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El documento ya no está disponible")
    try:
        contenido = await storage.descargar_objeto(fila.object_key)
    except storage.ObjetoNoEncontrado as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El documento ya no está disponible") from exc
    return Response(
        content=contenido,
        media_type=fila.content_type or "application/pdf",
        # `inline`, no `attachment`: se ve dentro de la propia página de firma
        # — obligar a descargarlo para poder firmarlo sería absurdo.
        headers={"Content-Disposition": f'inline; filename="{fila.nombre_archivo}"'},
    )


@publico_router.post("/{token}/codigo", response_model=CodigoEnviadoOut)
async def pedir_codigo(
    contexto: firma_service.ContextoFirma = Depends(firma_service.acceso_firma),
    session: AsyncSession = Depends(get_session),
) -> CodigoEnviadoOut:
    """Manda un código de un solo uso al DESTINATARIO — nunca a una dirección
    que venga en la petición. Ese es el punto: quien tenga el enlace solo
    puede firmar si además alcanza el canal de esa persona.

    Por dónde sale lo elige quien creó la solicitud (`canal_codigo`). En
    automático va por un canal que el enlace NO haya usado (ver
    `firma.reparto_para_codigo`): si los dos llegan al mismo sitio, el
    segundo factor no añade nada."""
    solicitud = contexto.solicitud
    firmante = contexto.firmante
    if firmante.estado not in (EstadoFirmante.PENDIENTE, EstadoFirmante.VISTA):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya has respondido a este documento")

    codigo = await firma_service.generar_otp(session, firmante)
    try:
        canales, destino = await firma_service.enviar_codigo(
            session, solicitud, firmante, codigo
        )
        return CodigoEnviadoOut(enviado=True, destino=destino, canales=canales)
    except Exception as exc:  # noqa: BLE001
        # El código YA está generado y es válido; lo que ha fallado es el
        # envío. Se informa sin tumbar la petición para que pueda reintentar
        # en vez de quedarse sin poder firmar.
        logger.warning("Fallo al enviar el código de %s: %s", solicitud.codigo, exc)
        return CodigoEnviadoOut(
            enviado=False,
            destino=ofuscar_email(firmante.email),
            error=str(exc),
        )


@publico_router.post("/{token}/firmar", response_model=ResultadoFirmaOut)
async def firmar_documento(
    datos: FirmarIn,
    request: Request,
    contexto: firma_service.ContextoFirma = Depends(firma_service.acceso_firma),
    session: AsyncSession = Depends(get_session),
) -> ResultadoFirmaOut:
    try:
        solicitud, completado = await firma_service.firmar(
            session,
            contexto,
            datos,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except firma_service.EstadoInvalido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    # Aviso a quienes YA habían firmado: se enteran de que el documento
    # avanza sin tener que preguntar. Nunca lanza — ver `avisar_firmantes`.
    firmantes = await firma_service.listar_firmantes(session, solicitud.id)
    await firma_service.avisar_firmantes(
        session, solicitud, firmantes, quien_acaba_de_firmar=contexto.firmante
    )

    # Y a los de casa, según las reglas que tengan puestas. Es otra cosa que
    # el aviso de arriba: aquel va a los firmantes (gente de fuera), este a
    # quien lleva el documento dentro de la organización.
    if solicitud.estado == EstadoFirma.FIRMADA:
        from app.modules.notificaciones.service import emitir

        await emitir(
            session,
            "firma.completada",
            organization_id=solicitud.organization_id,
            titulo=f"Documento firmado: {solicitud.titulo}",
            cuerpo=f"{solicitud.codigo} lo han firmado ya todas las partes.",
            enlace="/firmas",
        )

    pendientes = sum(
        1 for f in firmantes if f.estado in (EstadoFirmante.PENDIENTE, EstadoFirmante.VISTA)
    )
    return ResultadoFirmaOut(
        estado=solicitud.estado,
        completado=completado,
        mensaje=(
            "Documento firmado por todas las partes. Se ha guardado la copia sellada."
            if completado
            else f"Tu firma ha quedado registrada. Faltan {pendientes} firmante(s) por firmar."
        ),
    )


@publico_router.post("/{token}/rechazar", response_model=ResultadoFirmaOut)
async def rechazar_documento(
    datos: RechazarIn,
    contexto: firma_service.ContextoFirma = Depends(firma_service.acceso_firma),
    session: AsyncSession = Depends(get_session),
) -> ResultadoFirmaOut:
    try:
        await firma_service.rechazar(session, contexto, datos.motivo)
    except firma_service.EstadoInvalido as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    from app.modules.notificaciones.service import emitir

    await emitir(
        session,
        "firma.rechazada",
        organization_id=contexto.solicitud.organization_id,
        titulo=f"Firma rechazada: {contexto.solicitud.titulo}",
        cuerpo=f"{contexto.firmante.nombre} no ha firmado. Motivo: {datos.motivo}",
        enlace="/firmas",
        importante=True,
    )
    return ResultadoFirmaOut(
        estado=EstadoFirma.RECHAZADA, mensaje="Has rechazado la firma de este documento."
    )


# Router que se expone al registro de módulos: junta los dos espacios SIN que
# el público herede nada del privado. El público va sin guardas a propósito
# (quien firma no tiene cuenta): se autoriza contra el token de su enlace en
# `firma.acceso_firma`, y `app.main` comprueba al arrancar que no cuelga de
# ahí ninguna ruta que no esté en `RUTAS_PUBLICAS_PERMITIDAS`.
router = APIRouter()
router.include_router(router_privado)
router.include_router(publico_router)
