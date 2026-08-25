"""Separata del proveedor: el único espacio de la aplicación sin sesión.

Toda la autorización vive en `publico_acceso.acceso_proveedor`; aquí solo hay
lectura y escritura ya acotadas. Dos reglas que no se pueden relajar:

1. **Nunca se hace `commit`.** La variable `app.organization_id` es local a la
   transacción: un commit a media petición la vacía y todo lo que viniera
   después quedaría ciego. Cierra `get_session`, y solo él.
2. **Nada se serializa desde un modelo ORM.** Las respuestas se construyen con
   proyecciones de columnas explícitas. Serializar una `Partida` o un
   `Concepto` arrastraría los precios del emisor, y navegar por sus
   relaciones puede alcanzar filas de una organización hermana a través de la
   política de maestros compartidos (`app/core/rls.py`), que la cuenta activó
   para sus usuarios y no para un tercero sin cuenta.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.database import get_session
from app.modules.compras import oferta_service
from app.modules.compras.models import OfertaLinea, SolicitudLinea
from app.modules.compras.publico_acceso import ContextoProveedor, acceso_proveedor
from app.modules.documentos.models import Documento, EntidadDocumento
from app.modules.presupuestos.models_presupuesto import Presupuesto

router = APIRouter(prefix="/api/publico/oferta", tags=["publico"])


class LineaSeparataOut(BaseModel):
    id: str
    capitulo_resumen: str | None
    codigo: str | None
    resumen: str
    texto: str | None
    unidad: str
    medicion: Decimal
    precio_ofertado: Decimal | None
    observaciones_proveedor: str | None


class DocumentoSeparataOut(BaseModel):
    id: str
    nombre_archivo: str
    tamano_bytes: int


class SeparataOut(BaseModel):
    """Lo que ve el proveedor. Deliberadamente NO lleva ningún precio del
    emisor: solo qué trabajo es, cuánto hay, y para qué obra — sin eso no
    puede cotizar (no sabe ni dónde tiene que ir)."""

    codigo: str
    titulo: str
    estado: str
    fecha_limite: str | None
    notas: str | None
    emisor: str
    proveedor: str
    # Contexto de la obra. `cliente` es una decisión comercial del emisor:
    # le está diciendo al proveedor para quién trabaja.
    obra: str
    emplazamiento: str | None
    tipo_obra: str | None
    cliente: str | None
    lineas: list[LineaSeparataOut]
    documentos: list[DocumentoSeparataOut]


class LineaOfertaIn(BaseModel):
    id: str
    precio_ofertado: Decimal | None = Field(default=None, ge=0)
    observaciones_proveedor: str | None = Field(default=None, max_length=2000)


class GuardarOfertaIn(BaseModel):
    lineas: list[LineaOfertaIn] = Field(default_factory=list)


class EnviarOfertaOut(BaseModel):
    enviado: bool
    mensaje: str


async def _lineas(session: AsyncSession, ctx: ContextoProveedor) -> list[LineaSeparataOut]:
    """Las líneas del paquete cruzadas con lo que ESTE proveedor lleva
    ofertado. LEFT JOIN acotado a su destinatario: sin él vería (o pisaría)
    los precios de otro proveedor del mismo paquete."""
    filas = (
        await session.execute(
            select(
                SolicitudLinea.id,
                SolicitudLinea.capitulo_resumen,
                SolicitudLinea.codigo,
                SolicitudLinea.resumen,
                SolicitudLinea.texto,
                SolicitudLinea.unidad,
                SolicitudLinea.medicion,
                OfertaLinea.precio_ofertado,
                OfertaLinea.observaciones_proveedor,
            )
            .join(
                OfertaLinea,
                (OfertaLinea.linea_id == SolicitudLinea.id)
                & (OfertaLinea.destinatario_id == ctx.destinatario.id),
                isouter=True,
            )
            .where(SolicitudLinea.solicitud_id == ctx.solicitud.id)
            .order_by(SolicitudLinea.orden)
        )
    ).all()
    return [
        LineaSeparataOut(
            id=str(f.id),
            capitulo_resumen=f.capitulo_resumen,
            codigo=f.codigo,
            resumen=f.resumen,
            texto=f.texto,
            unidad=f.unidad,
            medicion=f.medicion,
            precio_ofertado=f.precio_ofertado,
            observaciones_proveedor=f.observaciones_proveedor,
        )
        for f in filas
    ]


async def _documentos(session: AsyncSession, ctx: ContextoProveedor) -> list[DocumentoSeparataOut]:
    filas = (
        await session.execute(
            select(Documento.id, Documento.nombre_archivo, Documento.tamano_bytes)
            .where(
                Documento.entidad == EntidadDocumento.SOLICITUD_PRECIOS,
                Documento.entidad_id == ctx.solicitud.id,
            )
            .order_by(Documento.created_at)
        )
    ).all()
    return [
        DocumentoSeparataOut(id=str(f.id), nombre_archivo=f.nombre_archivo, tamano_bytes=f.tamano_bytes)
        for f in filas
    ]


async def _separata(session: AsyncSession, ctx: ContextoProveedor) -> SeparataOut:
    from sqlalchemy import text

    emisor = await session.scalar(
        text("SELECT name FROM core.organization WHERE id = :org"),
        {"org": str(ctx.organization_id)},
    )
    proveedor = await session.scalar(
        text("SELECT razon_social FROM terceros.tercero WHERE id = :id"),
        {"id": str(ctx.destinatario.proveedor_id)},
    )
    # Proyección explícita, nunca el ORM: serializar el `Presupuesto` traería
    # sus precios y sus márgenes, que son del emisor (ver cabecera).
    obra = (
        await session.execute(
            select(
                Presupuesto.nombre,
                Presupuesto.emplazamiento,
                Presupuesto.tipo_obra,
                Presupuesto.cliente_id,
            ).where(Presupuesto.id == ctx.solicitud.presupuesto_id)
        )
    ).first()
    cliente = None
    if obra is not None and obra.cliente_id is not None:
        cliente = await session.scalar(
            text("SELECT razon_social FROM terceros.tercero WHERE id = :id"),
            {"id": str(obra.cliente_id)},
        )

    return SeparataOut(
        obra=obra.nombre if obra else "",
        emplazamiento=obra.emplazamiento if obra else None,
        tipo_obra=obra.tipo_obra if obra else None,
        cliente=cliente,
        codigo=ctx.solicitud.codigo,
        titulo=ctx.solicitud.titulo,
        # El estado que le importa al proveedor es el SUYO, no el del paquete:
        # otro puede haber contestado ya sin que eso cierre lo suyo.
        estado=str(ctx.destinatario.estado),
        fecha_limite=ctx.solicitud.fecha_limite.isoformat() if ctx.solicitud.fecha_limite else None,
        notas=ctx.solicitud.notas,
        emisor=emisor or "",
        proveedor=proveedor or "",
        lineas=await _lineas(session, ctx),
        documentos=await _documentos(session, ctx),
    )


@router.get("/{token}", response_model=SeparataOut)
async def ver_separata(
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    return await _separata(session, ctx)


@router.get("/{token}/documentos", response_model=list[DocumentoSeparataOut])
async def listar_documentos(
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentoSeparataOut]:
    """Documentos que el EMISOR adjuntó al borrador — de solo lectura aquí,
    nunca de subida (eso es el `/documento` que se dejó deliberadamente sin
    declarar, ver `publico_acceso.py`)."""
    return await _documentos(session, ctx)


@router.get("/{token}/documentos/{documento_id}/descargar")
async def descargar_documento(
    documento_id: uuid.UUID,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # El `documento_id` llega del cliente y no vale por sí solo: RLS ya acota
    # la organización, pero hace falta además comprobar que pertenece A ESTA
    # solicitud — si no, cualquier documento de otra solicitud de la misma
    # organización sería descargable con un token ajeno, mismo principio que
    # ya aplica `guardar_precios` a los ids de línea.
    fila = (
        await session.execute(
            select(Documento.object_key, Documento.nombre_archivo, Documento.content_type).where(
                Documento.id == documento_id,
                Documento.entidad == EntidadDocumento.SOLICITUD_PRECIOS,
                Documento.entidad_id == ctx.solicitud.id,
            )
        )
    ).first()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")

    try:
        contenido = await storage.descargar_objeto(fila.object_key)
    except storage.ObjetoNoEncontrado as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="El fichero ya no está en el almacén"
        ) from exc
    return Response(
        content=contenido,
        media_type=fila.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{fila.nombre_archivo}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{token}/lineas", response_model=SeparataOut)
async def guardar_precios(
    datos: GuardarOfertaIn,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    """Guarda lo que va rellenando el proveedor. No cierra nada: puede volver
    al enlace y seguir hasta que pulse enviar."""
    if not datos.lineas:
        return await _separata(session, ctx)

    # Las líneas se releen acotadas a ESTE paquete: los ids llegan del
    # cliente y no valen por sí solos, aunque el RLS ya acote la organización.
    por_id = {
        str(linea.id): linea
        for linea in (
            await session.execute(
                select(SolicitudLinea).where(SolicitudLinea.solicitud_id == ctx.solicitud.id)
            )
        ).scalars()
    }

    desconocidas = [d.id for d in datos.lineas if d.id not in por_id]
    if desconocidas:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Hay líneas que no pertenecen a esta solicitud.",
        )

    # Las ofertas de ESTE destinatario, no las del paquete: escribir sin este
    # filtro pisaría lo que haya ofertado otro proveedor.
    ofertas = {
        oferta.linea_id: oferta
        for oferta in (
            await session.execute(
                select(OfertaLinea).where(OfertaLinea.destinatario_id == ctx.destinatario.id)
            )
        ).scalars()
    }

    for entrada in datos.lineas:
        linea = por_id[entrada.id]
        oferta = ofertas.get(linea.id)
        if oferta is None:
            # Se crea al escribir, no antes: la ausencia de fila es "no lo ha
            # cotizado", que es el hueco que se enseña en el comparativo.
            oferta = OfertaLinea(
                organization_id=ctx.organization_id,
                destinatario_id=ctx.destinatario.id,
                linea_id=linea.id,
            )
            session.add(oferta)
            ofertas[linea.id] = oferta
        oferta.precio_ofertado = entrada.precio_ofertado
        oferta.observaciones_proveedor = entrada.observaciones_proveedor

    # La sesión va con `autoflush=False`, y la respuesta se construye con
    # proyecciones de columnas (no desde los objetos que acabamos de tocar):
    # sin este flush, el SELECT relee los valores viejos y el proveedor vería
    # que su precio "no se ha guardado" aunque sí lo esté.
    await session.flush()
    return await _separata(session, ctx)


@router.post("/{token}/enviar", response_model=EnviarOfertaOut)
async def enviar_oferta(
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> EnviarOfertaOut:
    """Cierra la respuesta de ESTE proveedor: genera su presupuesto-oferta a
    partir de lo que ha rellenado. Idempotente — reenviar el formulario no
    duplica nada, `oferta_service.cerrar_oferta` devuelve lo ya creado. Los
    demás destinatarios del paquete siguen a lo suyo."""
    from sqlalchemy import text

    proveedor_nombre = (
        await session.scalar(
            text("SELECT razon_social FROM terceros.tercero WHERE id = :id"),
            {"id": str(ctx.destinatario.proveedor_id)},
        )
        or "proveedor"
    )
    try:
        await oferta_service.cerrar_oferta(
            session, ctx.solicitud, ctx.destinatario, proveedor_nombre=proveedor_nombre
        )
    except oferta_service.SinLineasConPrecio as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await session.flush()
    return EnviarOfertaOut(
        enviado=True,
        mensaje="Gracias, tu oferta ha sido enviada. Ya puedes cerrar esta ventana.",
    )
