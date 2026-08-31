"""Rutas de las facturas de proveedor.

Aparte de `router.py` para no seguir engordándolo. Las URL son
`/api/facturas-recibidas/…`, distintas de `/api/facturas/…` (las de venta, que
vive en `facturacion`): son cosas distintas y compartir nombre al depurar sale
caro.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.compras import factura_recibida_service as facturas
from app.modules.compras import service
from app.modules.compras.models import (
    Albaran,
    EstadoFacturaRecibida,
    FacturaRecibida,
    FacturaRecibidaAlbaran,
)
from app.modules.compras.schemas import (
    FacturaRecibidaCreate,
    FacturaRecibidaOut,
    FacturaRecibidaUpdate,
    TotalesComprasObra,
)
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut
from app.modules.terceros.models import Tercero

guard = Depends(require_module("compras"))

router = APIRouter(
    prefix="/api/facturas-recibidas", tags=["compras"], dependencies=[guard]
)
# Igual que `costes_router`: la URL habla de obras porque es lo que el usuario
# consulta, y vive en compras porque es el módulo que ve las dos cosas.
totales_router = APIRouter(prefix="/api/obras", tags=["compras"], dependencies=[guard])


async def _salida(
    session: AsyncSession, factura: FacturaRecibida
) -> FacturaRecibidaOut:
    """Añade lo que la lista enseña y no está en la fila: el nombre del
    proveedor y los albaranes que cubre."""
    salida = FacturaRecibidaOut.model_validate(factura)
    salida.proveedor_razon_social = (
        await session.scalar(
            select(Tercero.razon_social).where(Tercero.id == factura.proveedor_id)
        )
        or ""
    )
    filas = (
        await session.execute(
            select(FacturaRecibidaAlbaran.albaran_id, Albaran.codigo)
            .join(Albaran, Albaran.id == FacturaRecibidaAlbaran.albaran_id)
            .where(FacturaRecibidaAlbaran.factura_id == factura.id)
            .order_by(Albaran.codigo)
        )
    ).all()
    salida.albaran_ids = [fila[0] for fila in filas]
    salida.albaran_codigos = [fila[1] for fila in filas]
    return salida


@router.get("", response_model=Page[FacturaRecibidaOut])
async def listar(
    obra_id: uuid.UUID | None = None,
    proveedor_id: uuid.UUID | None = None,
    estado: EstadoFacturaRecibida | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> Page[FacturaRecibidaOut]:
    items, total = await facturas.listar(
        session,
        obra_id=obra_id,
        proveedor_id=proveedor_id,
        estado=estado,
        limit=limit,
        offset=offset,
    )
    return Page(
        items=[await _salida(session, f) for f in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=FacturaRecibidaOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: FacturaRecibidaCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "crear")),
) -> FacturaRecibidaOut:
    try:
        factura = await facturas.crear(
            session,
            obra_id=datos.obra_id,
            proveedor_id=datos.proveedor_id,
            numero_proveedor=datos.numero_proveedor,
            fecha=datos.fecha,
            base_imponible=datos.base_imponible,
            tipo_iva=datos.tipo_iva,
            inversion_sujeto_pasivo=datos.inversion_sujeto_pasivo,
            cuota_iva=datos.cuota_iva,
            total=datos.total,
            fecha_vencimiento=datos.fecha_vencimiento,
            notas=datos.notas,
            albaran_ids=datos.albaran_ids,
        )
    except (service.ObraInvalida, service.ProveedorInvalido) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except facturas.AlbaranInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except facturas.FacturaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    salida = await _salida(session, factura)
    await session.commit()
    return salida


async def _factura_o_404(
    session: AsyncSession, factura_id: uuid.UUID
) -> FacturaRecibida:
    factura = await facturas.obtener(session, factura_id)
    if factura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Factura no encontrada")
    return factura


@router.get("/{factura_id}", response_model=FacturaRecibidaOut)
async def leer(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> FacturaRecibidaOut:
    factura = await _factura_o_404(session, factura_id)
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    return await _salida(session, factura)


@router.get("/{factura_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> list[RegistroAuditoriaOut]:
    factura = await _factura_o_404(session, factura_id)
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(FacturaRecibida), registro_id=factura_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@router.patch("/{factura_id}", response_model=FacturaRecibidaOut)
async def actualizar(
    factura_id: uuid.UUID,
    datos: FacturaRecibidaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "editar")),
) -> FacturaRecibidaOut:
    factura = await _factura_o_404(session, factura_id)
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    try:
        await facturas.actualizar(
            session, factura, datos.model_dump(exclude_unset=True)
        )
    except facturas.AlbaranInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except facturas.FacturaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    salida = await _salida(session, factura)
    await session.commit()
    return salida


@router.delete("/{factura_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    factura_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("compras", "borrar")),
) -> None:
    factura = await _factura_o_404(session, factura_id)
    verificar_propiedad(alcance, principal, factura.creado_por_subject)
    await facturas.eliminar(session, factura)
    await session.commit()


@totales_router.get("/{obra_id}/compras", response_model=TotalesComprasObra)
async def totales_de_compras(
    obra_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("compras", "ver")),
) -> TotalesComprasObra:
    """El cuadre de la obra: lo entregado frente a lo facturado."""
    from app.modules.obras.service import obtener_obra

    if await obtener_obra(session, obra_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Obra no encontrada")

    albaranes_total = await service.total_albaranes_de_obra(session, obra_id)
    totales = await facturas.totales_de_obra(session, obra_id)
    sin_facturar = await facturas.albaranes_sin_facturar(session, obra_id)
    return TotalesComprasObra(
        albaranes_total=albaranes_total,
        facturas_base=totales["base"],
        facturas_total=totales["total"],
        pendiente_de_pago=totales["pendiente_de_pago"],
        albaranes_sin_facturar=len(sin_facturar),
    )
