"""Biblioteca de planos.

El permiso de módulo cubre lo obvio (quién ve, sube y borra planos), pero hay
una puerta que no basta con la de aquí: **llevar una medición a una partida es
escribir en un presupuesto**. Ese endpoint exige además permiso de edición en
`presupuestos`, porque si no el módulo de planos sería la manera de modificar
un presupuesto sin permiso para tocarlo.
"""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.tenancy import require_organization_id
from app.modules.planos import dxf as lector_dxf
from app.modules.planos import geometria, service
from app.modules.planos import ia as lector_ia
from app.modules.planos.enums import OrigenPlano
from app.modules.planos.models import CapaPlano, Plano
from app.modules.planos.schemas import (
    AplicadaOut,
    AplicarIn,
    CalibracionIn,
    CapaIn,
    CapaOut,
    CotaLeidaOut,
    ElementoIn,
    ElementoOut,
    EscalaImpresaIn,
    HojaOut,
    LecturaIaOut,
    PlanoDetalle,
    PlanoOut,
    PlanoUpdate,
)

router = APIRouter(
    prefix="/api/planos", tags=["planos"], dependencies=[Depends(require_module("planos"))]
)


@router.get("", response_model=list[PlanoOut])
async def listar(
    obra_id: uuid.UUID | None = None,
    presupuesto_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "ver")),
) -> list[PlanoOut]:
    consulta = select(Plano).where(Plano.organization_id == require_organization_id())
    if obra_id is not None:
        consulta = consulta.where(Plano.obra_id == obra_id)
    if presupuesto_id is not None:
        consulta = consulta.where(Plano.presupuesto_id == presupuesto_id)
    if alcance == Alcance.PROPIOS:
        consulta = consulta.where(Plano.creado_por_subject == principal.subject)
    filas = await session.scalars(consulta.order_by(Plano.created_at.desc()).limit(500))
    return [PlanoOut.model_validate(f) for f in filas]


@router.post("", response_model=PlanoDetalle, status_code=status.HTTP_201_CREATED)
async def subir(
    nombre: str = Form(...),
    descripcion: str | None = Form(default=None),
    obra_id: uuid.UUID | None = Form(default=None),
    presupuesto_id: uuid.UUID | None = Form(default=None),
    #: JSON con las páginas que el navegador ha leído del fichero:
    #: `[{"ancho": 842, "alto": 595, "nombre": null}, ...]`. Ver
    #: `service.crear_plano` para por qué se acepta del cliente.
    hojas: str = Form(...),
    fichero: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "crear")),
) -> PlanoDetalle:
    try:
        paginas = json.loads(hojas)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Páginas ilegibles") from exc
    if not isinstance(paginas, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Páginas ilegibles")

    contenido = await fichero.read()
    try:
        plano = await service.crear_plano(
            session,
            nombre=nombre,
            descripcion=descripcion,
            obra_id=obra_id,
            presupuesto_id=presupuesto_id,
            nombre_archivo=fichero.filename or "plano",
            content_type=fichero.content_type or "application/octet-stream",
            contenido=contenido,
            hojas=paginas,
        )
    except (service.PlanoInvalido, lector_dxf.DxfInvalido) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return PlanoDetalle.model_validate(plano)


@router.get("/{plano_id}", response_model=PlanoDetalle)
async def ver(
    plano_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "ver")),
) -> PlanoDetalle:
    plano = await _plano(session, plano_id, principal, alcance)
    await session.refresh(plano, ["hojas", "capas"])
    return PlanoDetalle.model_validate(plano)


@router.get("/{plano_id}/archivo")
async def archivo(
    plano_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "ver")),
) -> Response:
    """El fichero original, tal cual se subió. Lo pinta pdf.js en el navegador:
    no se rasteriza aquí, ni se recomprime, ni se toca."""
    plano = await _plano(session, plano_id, principal, alcance)
    try:
        contenido = await storage.descargar_objeto(plano.object_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "El fichero no está disponible ahora mismo"
        ) from exc
    return Response(
        content=contenido,
        media_type=plano.content_type,
        headers={"Content-Disposition": f'inline; filename="{plano.nombre_archivo}"'},
    )


@router.patch("/{plano_id}", response_model=PlanoDetalle)
async def actualizar(
    plano_id: uuid.UUID,
    datos: PlanoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> PlanoDetalle:
    plano = await _plano(session, plano_id, principal, alcance)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(plano, campo, valor)
    await session.flush()
    await session.refresh(plano, ["hojas", "capas"])
    return PlanoDetalle.model_validate(plano)


@router.delete("/{plano_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar(
    plano_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "borrar")),
) -> None:
    plano = await _plano(session, plano_id, principal, alcance)
    await service.borrar_plano(session, plano)


# ── Capas ───────────────────────────────────────────────────────────────


@router.post("/{plano_id}/capas", response_model=CapaOut, status_code=status.HTTP_201_CREATED)
async def crear_capa(
    plano_id: uuid.UUID,
    datos: CapaIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> CapaOut:
    plano = await _plano(session, plano_id, principal, alcance)
    capa = CapaPlano(
        organization_id=plano.organization_id, plano_id=plano.id, **datos.model_dump()
    )
    session.add(capa)
    await session.flush()
    return CapaOut.model_validate(capa)


@router.put("/capas/{capa_id}", response_model=CapaOut)
async def actualizar_capa(
    capa_id: uuid.UUID,
    datos: CapaIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> CapaOut:
    capa = await session.scalar(
        select(CapaPlano).where(
            CapaPlano.id == capa_id,
            CapaPlano.organization_id == require_organization_id(),
        )
    )
    if capa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Capa no encontrada")
    for campo, valor in datos.model_dump().items():
        setattr(capa, campo, valor)
    await session.flush()
    return CapaOut.model_validate(capa)


@router.delete("/capas/{capa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_capa(
    capa_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> None:
    """Borrar una capa NO borra lo dibujado en ella: los elementos se quedan
    sin capa (`ON DELETE SET NULL`). Perder mediciones por ordenar las capas
    sería una trampa."""
    capa = await session.scalar(
        select(CapaPlano).where(
            CapaPlano.id == capa_id,
            CapaPlano.organization_id == require_organization_id(),
        )
    )
    if capa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Capa no encontrada")
    await session.delete(capa)
    await session.flush()


# ── Hojas: calibrar y dibujar ───────────────────────────────────────────


@router.post("/hojas/{hoja_id}/calibrar", response_model=HojaOut)
async def calibrar(
    hoja_id: uuid.UUID,
    datos: CalibracionIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> HojaOut:
    hoja = await service.obtener_hoja(session, hoja_id)
    if hoja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hoja no encontrada")
    try:
        await service.calibrar(
            session,
            hoja,
            a=datos.a.model_dump(mode="json"),
            b=datos.b.model_dump(mode="json"),
            distancia_m=datos.distancia_m,
        )
    except geometria.GeometriaInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return HojaOut.model_validate(hoja)


@router.post("/hojas/{hoja_id}/leer-con-ia", response_model=LecturaIaOut)
async def leer_con_ia(
    hoja_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> LecturaIaOut:
    """Lee el plano con IA. **No escribe nada**: devuelve lo que ha leído para
    que alguien lo aplique o lo descarte.

    A la IA no se le piden coordenadas, solo texto — ver el docstring de
    `planos/ia.py` para por qué.
    """
    from app.modules.core import billing_service

    hoja = await service.obtener_hoja(session, hoja_id)
    if hoja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hoja no encontrada")
    plano = await service.obtener_plano(session, hoja.plano_id)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano no encontrado")
    if plano.origen == OrigenPlano.DXF:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Un DXF ya trae sus unidades y su geometría: no hay nada que leer con IA.",
        )

    try:
        contenido = await storage.descargar_objeto(plano.object_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "El fichero no está disponible ahora mismo"
        ) from exc

    try:
        lectura = await lector_ia.interpretar(session, contenido, plano.content_type)
    except lector_ia.LecturaFallida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await billing_service.registrar_uso_ia(
        session,
        organization_id=require_organization_id(),
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
        proveedor="gemini",
        modelo=lectura.modelo,
        tokens_entrada=lectura.tokens_entrada,
        tokens_salida=lectura.tokens_salida,
        referencia=str(plano.id),
    )

    return LecturaIaOut(
        escala_impresa=lectura.escala_impresa,
        escala_texto=lectura.escala_texto,
        escala_aplicable=lectura.escala_impresa is not None
        and plano.origen == OrigenPlano.PDF,
        cotas=[CotaLeidaOut(texto=c.texto, metros=c.metros, donde=c.donde) for c in lectura.cotas],
        resumen=lectura.resumen,
        avisos=lectura.avisos,
    )


@router.post("/hojas/{hoja_id}/calibrar-por-escala", response_model=HojaOut)
async def calibrar_por_escala(
    hoja_id: uuid.UUID,
    datos: EscalaImpresaIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> HojaOut:
    """Calibra con la escala impresa del plano. Exacto: la cuenta es geometría
    del papel, sin estimar ningún píxel."""
    hoja = await service.obtener_hoja(session, hoja_id)
    if hoja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hoja no encontrada")
    plano = await service.obtener_plano(session, hoja.plano_id)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano no encontrado")
    try:
        await service.calibrar_por_escala_impresa(session, hoja, plano, datos.denominador)
    except (service.PlanoInvalido, lector_ia.LecturaFallida) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return HojaOut.model_validate(hoja)


@router.get("/hojas/{hoja_id}/elementos", response_model=list[ElementoOut])
async def listar_elementos(
    hoja_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "ver")),
) -> list[ElementoOut]:
    return [ElementoOut.model_validate(e) for e in await service.elementos_de(session, hoja_id)]


@router.post(
    "/hojas/{hoja_id}/elementos",
    response_model=ElementoOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_elemento(
    hoja_id: uuid.UUID,
    datos: ElementoIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> ElementoOut:
    hoja = await service.obtener_hoja(session, hoja_id)
    if hoja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hoja no encontrada")
    try:
        elemento = await service.guardar_elemento(
            session,
            hoja,
            tipo=datos.tipo,
            forma=[p.model_dump(mode="json") for p in datos.geometria],
            capa_id=datos.capa_id,
            texto=datos.texto,
            color=datos.color,
        )
    except geometria.GeometriaInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ElementoOut.model_validate(elemento)


@router.put("/elementos/{elemento_id}", response_model=ElementoOut)
async def actualizar_elemento(
    elemento_id: uuid.UUID,
    datos: ElementoIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> ElementoOut:
    elemento = await service.obtener_elemento(session, elemento_id)
    if elemento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    hoja = await service.obtener_hoja(session, elemento.hoja_id)
    if hoja is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hoja no encontrada")
    try:
        await service.guardar_elemento(
            session,
            hoja,
            tipo=datos.tipo,
            forma=[p.model_dump(mode="json") for p in datos.geometria],
            capa_id=datos.capa_id,
            texto=datos.texto,
            color=datos.color,
            elemento=elemento,
        )
    except geometria.GeometriaInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ElementoOut.model_validate(elemento)


@router.delete("/elementos/{elemento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_elemento(
    elemento_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("planos", "editar")),
) -> None:
    elemento = await service.obtener_elemento(session, elemento_id)
    if elemento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    await session.delete(elemento)
    await session.flush()


@router.post("/elementos/{elemento_id}/aplicar", response_model=AplicadaOut)
async def aplicar(
    elemento_id: uuid.UUID,
    datos: AplicarIn,
    session: AsyncSession = Depends(get_session),
    alcance_planos: Alcance = Depends(require_permiso("planos", "ver")),
    # El segundo permiso es el que de verdad importa: esto escribe en un
    # presupuesto. Sin él, planos sería la puerta de atrás para medir dentro
    # de un presupuesto que no puedes tocar.
    alcance_presupuestos: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> AplicadaOut:
    elemento = await service.obtener_elemento(session, elemento_id)
    if elemento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    try:
        linea_id = await service.aplicar_a_partida(session, elemento, datos.partida_id)
    except service.MedicionNoAplicable as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AplicadaOut(
        linea_medicion_id=linea_id, valor=elemento.valor, unidad=elemento.unidad or ""
    )


async def _plano(
    session: AsyncSession, plano_id: uuid.UUID, principal: Principal, alcance: Alcance
) -> Plano:
    plano = await service.obtener_plano(session, plano_id)
    if plano is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plano no encontrado")
    verificar_propiedad(alcance, principal, plano.creado_por_subject)
    return plano
