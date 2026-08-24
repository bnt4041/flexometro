import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.modules.presupuestos import fiebdc
from app.modules.presupuestos import presupuesto_service as service
from app.modules.presupuestos.fiebdc.importador import EstrategiaCodigos

# 80 MB: un banco autonómico completo ronda los 20-30 MB; el tope evita que
# una subida equivocada se coma la memoria del proceso.
TAMANO_MAXIMO = 80 * 1024 * 1024

router = APIRouter(
    prefix="/api/fiebdc", tags=["fiebdc"], dependencies=[Depends(require_module("presupuestos"))]
)


class AnalisisOut(BaseModel):
    """Lo que dice el fichero, sin escribir nada."""

    version: str
    fecha: str
    programa: str
    cabecera: str
    codificacion: str
    es_presupuesto: bool
    total_conceptos: int
    por_tipo: dict[str, int]
    lineas_descomposicion: int
    mediciones: int
    incidencias: list[str]


class ImportacionOut(BaseModel):
    conceptos_creados: int
    conceptos_omitidos: int
    conceptos_actualizados: int
    lineas_descomposicion: int
    presupuesto_id: uuid.UUID | None
    capitulos: int
    partidas: int
    lineas_medicion: int
    discrepancias: int
    discrepancia_maxima: str
    ejemplos_discrepancia: list[dict]
    ciclos: list[str]
    incidencias: list[str]


async def _leer(fichero: UploadFile) -> bytes:
    datos = await fichero.read()
    if not datos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El fichero está vacío"
        )
    if len(datos) > TAMANO_MAXIMO:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El fichero supera el máximo de {TAMANO_MAXIMO // (1024 * 1024)} MB",
        )
    return datos


@router.post("/analizar", response_model=AnalisisOut)
async def analizar(fichero: UploadFile = File(...)) -> AnalisisOut:
    """Lee el fichero y cuenta lo que trae, sin tocar la base de datos.

    Sirve para mirar antes de importar: qué versión es, cuántos conceptos hay y
    qué no se ha sabido interpretar.
    """
    archivo = fiebdc.parsear(await _leer(fichero))
    return AnalisisOut(
        version=archivo.version,
        fecha=archivo.fecha,
        programa=archivo.programa,
        cabecera=archivo.cabecera,
        codificacion=archivo.codificacion,
        es_presupuesto=archivo.es_presupuesto,
        total_conceptos=len(archivo.conceptos),
        por_tipo=archivo.resumen_por_tipo(),
        lineas_descomposicion=sum(len(v) for v in archivo.descomposiciones.values()),
        mediciones=len(archivo.mediciones),
        incidencias=[
            f"línea {i.linea} {i.registro}: {i.detalle}" for i in archivo.incidencias[:50]
        ],
    )


@router.post("/importar", response_model=ImportacionOut)
async def importar(
    fichero: UploadFile = File(...),
    estrategia: EstrategiaCodigos = Form(default=EstrategiaCodigos.OMITIR),
    crear_presupuesto: bool = Form(default=True),
    nombre_presupuesto: str | None = Form(default=None),
    # Fase 50: soltar un BC3 sobre un capítulo del banco coloca ahí las
    # fichas del fichero. Sin él, caen en la raíz como hasta ahora.
    capitulo_banco_id: uuid.UUID | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
) -> ImportacionOut:
    archivo = fiebdc.parsear(await _leer(fichero))
    resultado = await fiebdc.importar(
        session,
        archivo,
        estrategia=estrategia,
        crear_presupuesto=crear_presupuesto,
        nombre_presupuesto=nombre_presupuesto,
        capitulo_banco_id=capitulo_banco_id,
    )

    if resultado.ciclos:
        # Con ciclos no se ha escrito nada; se devuelve 422 para que quede
        # claro que la importación no ha ocurrido.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "El fichero tiene ciclos en la descomposición y no se puede importar: "
                + "; ".join(resultado.ciclos[:5])
            ),
        )

    # Sin este commit, un cliente que navegue al presupuesto recién creado en
    # cuanto recibe la respuesta (lo normal aquí) puede llegar antes de que
    # `get_session` confirme la transacción y encontrarse un 404.
    await session.commit()
    return _salida(resultado)


@router.post("/importar-en-capitulo/{capitulo_id}", response_model=ImportacionOut)
async def importar_en_capitulo(
    capitulo_id: uuid.UUID,
    fichero: UploadFile = File(...),
    estrategia: EstrategiaCodigos = Form(default=EstrategiaCodigos.OMITIR),
    session: AsyncSession = Depends(get_session),
) -> ImportacionOut:
    """Arrastrar un BC3 sobre un capítulo del presupuesto (en vez de "Importar
    BC3" como pantalla aparte): cuelga los subcapítulos y partidas del
    fichero de ese capítulo, detrás de lo que ya tuviera. El catálogo de
    precios se sube igual que en `/importar`."""
    archivo = fiebdc.parsear(await _leer(fichero))
    resultado = await fiebdc.importar_bajo_capitulo(
        session, archivo, capitulo_id, estrategia=estrategia
    )

    if resultado.ciclos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "El fichero tiene ciclos en la descomposición y no se puede importar: "
                + "; ".join(resultado.ciclos[:5])
            ),
        )
    if resultado.presupuesto_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="; ".join(resultado.incidencias[:3]) or "El capítulo destino no existe",
        )

    await session.commit()
    return _salida(resultado)


@router.post("/importar-en-presupuesto/{presupuesto_id}", response_model=ImportacionOut)
async def importar_en_presupuesto(
    presupuesto_id: uuid.UUID,
    fichero: UploadFile = File(...),
    estrategia: EstrategiaCodigos = Form(default=EstrategiaCodigos.OMITIR),
    session: AsyncSession = Depends(get_session),
) -> ImportacionOut:
    """Arrastrar un BC3 sobre la fila raíz del presupuesto (en vez de sobre un
    capítulo, o "Importar BC3" como pantalla aparte): cuelga los capítulos
    del fichero como capítulos de primer nivel, detrás de los que ya
    hubiera."""
    archivo = fiebdc.parsear(await _leer(fichero))
    resultado = await fiebdc.importar_en_raiz(
        session, archivo, presupuesto_id, estrategia=estrategia
    )

    if resultado.ciclos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "El fichero tiene ciclos en la descomposición y no se puede importar: "
                + "; ".join(resultado.ciclos[:5])
            ),
        )
    if resultado.presupuesto_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="; ".join(resultado.incidencias[:3]) or "El presupuesto destino no existe",
        )

    await session.commit()
    return _salida(resultado)


def _salida(resultado) -> ImportacionOut:
    return ImportacionOut(
        conceptos_creados=resultado.conceptos_creados,
        conceptos_omitidos=resultado.conceptos_omitidos,
        conceptos_actualizados=resultado.conceptos_actualizados,
        lineas_descomposicion=resultado.lineas_descomposicion,
        presupuesto_id=resultado.presupuesto_id,
        capitulos=resultado.capitulos,
        partidas=resultado.partidas,
        lineas_medicion=resultado.lineas_medicion,
        discrepancias=len(resultado.discrepancias),
        discrepancia_maxima=str(resultado.discrepancia_maxima),
        ejemplos_discrepancia=[
            {"codigo": c, "calculado": str(nuestro), "en_fichero": str(suyo)}
            for c, nuestro, suyo in resultado.discrepancias[:20]
        ],
        ciclos=resultado.ciclos,
        incidencias=resultado.incidencias[:50],
    )


@router.get("/exportar/{presupuesto_id}")
async def exportar(
    presupuesto_id: uuid.UUID,
    codificacion: str = Query(default="cp1252", pattern="^(cp1252|utf-8)$"),
    venta: bool = Query(default=False),
    descompuestos: bool = Query(default=True),
    mediciones: bool = Query(default=True),
    descripcion: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> Response:
    """Presupuesto completo en BC3, con su cuadro de precios y sus mediciones."""
    presupuesto = await service.obtener(session, presupuesto_id)
    if presupuesto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado"
        )
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject)

    datos = await fiebdc.exportar_presupuesto(
        session,
        presupuesto,
        codificacion=codificacion,
        incluir_venta=venta,
        incluir_descompuestos=descompuestos,
        incluir_mediciones=mediciones,
        incluir_descripcion=descripcion,
    )
    return Response(
        content=datos,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{presupuesto.codigo}.bc3"'
        },
    )
