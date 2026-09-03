import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_admin_organizacion
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.modules.core.tenant_utils import cuenta_id_del_principal
from app.modules.presupuestos import plantilla_docx_service as service
from app.modules.presupuestos import presupuesto_service
from app.modules.presupuestos.plantilla_docx_schemas import FormatoDescarga, PlantillaPresupuestoOut

# 15 MB: un .docx con logo e imágenes de cabecera no pasa de unos pocos MB.
TAMANO_MAXIMO = 15 * 1024 * 1024

router = APIRouter(
    prefix="/api/presupuestos",
    tags=["plantillas-presupuesto"],
    dependencies=[Depends(require_module("presupuestos"))],
)

tenant_router = APIRouter(
    prefix="/api/ajustes/plantillas-presupuesto",
    tags=["plantillas-presupuesto"],
    dependencies=[Depends(require_admin_organizacion)],
)


@tenant_router.get("", response_model=list[PlantillaPresupuestoOut])
async def listar_tenant(
    principal: Principal = Depends(get_principal), session: AsyncSession = Depends(get_session)
) -> list[PlantillaPresupuestoOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    plantillas = await service.listar_plantillas(session, cuenta_id)
    return [PlantillaPresupuestoOut.model_validate(p) for p in plantillas]


@tenant_router.post("", response_model=PlantillaPresupuestoOut, status_code=status.HTTP_201_CREATED)
async def subir_tenant(
    nombre: str = Form(..., min_length=1, max_length=120),
    archivo: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> PlantillaPresupuestoOut:
    if not archivo.filename or not archivo.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Solo se admiten archivos .docx")
    contenido = await archivo.read()
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El archivo supera los 15 MB")

    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        plantilla = await service.subir_plantilla(session, cuenta_id, nombre, contenido)
    except service.PlantillaInvalida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "mensaje": exc.mensaje_usuario,
                "nota_tecnica": exc.nota_tecnica,
                "reparable": exc.reparable,
            },
        ) from exc
    await session.commit()
    return PlantillaPresupuestoOut.model_validate(plantilla)


@tenant_router.post(
    "/reparar", response_model=PlantillaPresupuestoOut, status_code=status.HTTP_201_CREATED
)
async def reparar_y_subir_tenant(
    nombre: str = Form(..., min_length=1, max_length=120),
    archivo: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> PlantillaPresupuestoOut:
    """Repara automáticamente el error más común (etiquetas {%tr/%p ...%} de
    apertura y cierre compartiendo fila/párrafo, ver `PlantillaInvalida` en
    el servicio) y sube el resultado ya arreglado. Solo tiene sentido
    llamarla tras un 422 de `subir_tenant` con `reparable: true`."""
    if not archivo.filename or not archivo.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Solo se admiten archivos .docx"
        )
    contenido = await archivo.read()
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El archivo supera los 15 MB"
        )

    contenido_reparado = service.reparar_tags_docxtpl(contenido)

    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        plantilla = await service.subir_plantilla(session, cuenta_id, nombre, contenido_reparado)
    except service.PlantillaInvalida as exc:
        # La reparación automática solo cubre el caso de etiquetas mal
        # separadas; si el fallo era otra cosa (o hay más de un problema),
        # se devuelve igual que un intento normal, con su nota técnica.
        mensaje = "La reparación automática no ha sido suficiente: " + exc.mensaje_usuario
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"mensaje": mensaje, "nota_tecnica": exc.nota_tecnica, "reparable": False},
        ) from exc
    await session.commit()
    return PlantillaPresupuestoOut.model_validate(plantilla)


@tenant_router.get("/{plantilla_id}/descargar")
async def descargar_patron_tenant(
    plantilla_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """El .docx tal cual está guardado, sin rellenar — para abrirlo en Word y
    diseñarlo (una plantilla de sistema sirve de patrón de partida)."""
    cuenta_id = await cuenta_id_del_principal(session, principal)
    plantilla = await service.obtener_plantilla(session, plantilla_id, cuenta_id)
    if plantilla is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plantilla no encontrada")
    from app.core import storage

    contenido = await storage.descargar_objeto(plantilla.archivo_docx_key)
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{plantilla.nombre}.docx"'},
    )


@tenant_router.delete("/{plantilla_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_tenant(
    plantilla_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> None:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    borrada = await service.eliminar_plantilla(session, cuenta_id, plantilla_id)
    if not borrada:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plantilla no encontrada")
    await session.commit()


# --- Listado y descarga desde el propio presupuesto ---


@router.get("/{presupuesto_id}/plantillas", response_model=list[PlantillaPresupuestoOut])
async def listar_para_presupuesto(
    presupuesto_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
    session: AsyncSession = Depends(get_session),
) -> list[PlantillaPresupuestoOut]:
    presupuesto = await presupuesto_service.obtener(session, presupuesto_id)
    if presupuesto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado")
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject)
    cuenta_id = await cuenta_id_del_principal(session, principal)
    plantillas = await service.listar_plantillas(session, cuenta_id)
    return [PlantillaPresupuestoOut.model_validate(p) for p in plantillas]


@router.get("/{presupuesto_id}/plantilla/{plantilla_id}")
async def descargar_plantilla(
    presupuesto_id: uuid.UUID,
    plantilla_id: uuid.UUID,
    formato: FormatoDescarga = Query(default="pdf"),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    presupuesto = await presupuesto_service.obtener(session, presupuesto_id)
    if presupuesto is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado")
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject)

    cuenta_id = await cuenta_id_del_principal(session, principal)
    plantilla = await service.obtener_plantilla(session, plantilla_id, cuenta_id)
    if plantilla is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plantilla no encontrada")

    try:
        contenido = await service.generar_documento(session, presupuesto, plantilla, formato)
    except service.ConversionPdfFallida as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    extension = "pdf" if formato == "pdf" else "docx"
    tipo = (
        "application/pdf"
        if formato == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    nombre = f"{presupuesto.codigo}-{plantilla.nombre}.{extension}"
    return Response(
        content=contenido,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
