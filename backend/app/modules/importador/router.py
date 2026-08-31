import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.importador import destinos, lectura, service
from app.modules.importador.models import Importacion

router = APIRouter(
    prefix="/api/importador",
    tags=["importador"],
    dependencies=[Depends(require_module("importador"))],
)

#: Tope de subida. Una hoja de 5.000 filas ocupa mucho menos; esto solo evita
#: que alguien mande un fichero enorme por error.
MAX_BYTES = 8 * 1024 * 1024


class CampoOut(BaseModel):
    nombre: str
    etiqueta: str
    tipo: str
    obligatorio: bool
    ayuda: str


class DestinoOut(BaseModel):
    codigo: str
    modulo: str
    etiqueta: str
    descripcion: str
    campos: list[CampoOut]


class ImportacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    destino: str
    nombre_archivo: str
    estado: str
    columnas: list
    mapeo: dict
    creadas: int
    con_error: int
    error: str | None = None
    #: Solo las primeras filas: la hoja entera puede ser larga y el navegador
    #: solo necesita ver si el mapeo cuadra.
    vista_previa: list = []
    total_filas: int = 0
    #: Problemas detectables sin tocar la base.
    problemas: list = []
    resultado: list = []


class MapeoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapeo: dict[str, str]


def _salida(importacion: Importacion) -> ImportacionOut:
    salida = ImportacionOut.model_validate(importacion)
    filas = importacion.filas or []
    salida.total_filas = len(filas)
    salida.vista_previa = filas[: service.FILAS_VISTA_PREVIA]
    salida.problemas = service.validar(importacion) if importacion.mapeo else []
    return salida


@router.get("/destinos", response_model=list[DestinoOut])
async def listar_destinos(
    alcance: Alcance = Depends(require_permiso("importador", "ver")),
) -> list[DestinoOut]:
    return [
        DestinoOut(
            codigo=d.codigo,
            modulo=d.modulo,
            etiqueta=d.etiqueta,
            descripcion=d.descripcion,
            campos=[c.__dict__ for c in d.campos],
        )
        for d in destinos.catalogo()
    ]


@router.get("/importaciones", response_model=list[ImportacionOut])
async def listar(
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("importador", "ver")),
) -> list[ImportacionOut]:
    filas = await session.scalars(
        select(Importacion)
        .where(Importacion.organization_id == require_organization_id())
        .order_by(Importacion.created_at.desc())
        .limit(50)
    )
    return [_salida(f) for f in filas]


@router.post(
    "/importaciones", response_model=ImportacionOut, status_code=status.HTTP_201_CREATED
)
async def subir(
    destino: str = Form(...),
    archivo: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("importador", "crear")),
) -> ImportacionOut:
    """Lee la hoja y propone un mapeo. Todavía no importa nada."""
    if destinos.obtener(destino) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Destino desconocido: {destino}")

    contenido = await archivo.read()
    if len(contenido) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El fichero pasa de 8 MB"
        )
    try:
        columnas, filas = lectura.leer(archivo.filename or "", contenido)
    except lectura.ArchivoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if not filas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "La hoja no tiene ninguna fila de datos"
        )

    importacion = Importacion(
        organization_id=require_organization_id(),
        destino=destino,
        nombre_archivo=archivo.filename or "hoja",
        columnas=columnas,
        filas=filas,
        # Se propone solo: en una hoja normal acierta casi todo y lo que no,
        # se corrige a mano antes de importar.
        mapeo=lectura.sugerir_mapeo(columnas, destinos.obtener(destino).campos),
        **datos_autoria(),
    )
    session.add(importacion)
    await session.flush()
    return _salida(importacion)


@router.put("/importaciones/{importacion_id}/mapeo", response_model=ImportacionOut)
async def guardar_mapeo(
    importacion_id: uuid.UUID,
    datos: MapeoIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("importador", "editar")),
) -> ImportacionOut:
    """Guarda el mapeo y devuelve los problemas, sin escribir nada aún."""
    importacion = await _importacion(session, importacion_id)
    importacion.mapeo = {k: v for k, v in datos.mapeo.items() if v}
    await session.flush()
    return _salida(importacion)


@router.post("/importaciones/{importacion_id}/ejecutar", response_model=ImportacionOut)
async def ejecutar(
    importacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("importador", "crear")),
) -> ImportacionOut:
    """Importa de verdad. Cada fila va en su propio savepoint: si una falla,
    las demás entran igual."""
    importacion = await _importacion(session, importacion_id)
    if importacion.ejecutada_en is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esta importación ya se ejecutó. Sube la hoja otra vez para repetirla.",
        )
    return _salida(await service.ejecutar(session, importacion))


@router.delete("/importaciones/{importacion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar(
    importacion_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("importador", "borrar")),
) -> None:
    """Borra el registro de la importación. Lo importado NO se deshace: son
    terceros y personas ya dados de alta, con su propia vida a partir de ahí."""
    await session.delete(await _importacion(session, importacion_id))
    await session.flush()


async def _importacion(session: AsyncSession, importacion_id: uuid.UUID) -> Importacion:
    importacion = await service.obtener(session, importacion_id)
    if importacion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrada")
    return importacion
