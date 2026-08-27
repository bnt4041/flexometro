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

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.html_seguro import sanear_html
from app.core.database import get_session
from app.modules.compras import oferta_service
from app.modules.compras.models import (
    OfertaDescompuesto,
    OfertaLinea,
    OfertaMedicion,
    SolicitudLinea,
)
from app.modules.compras import publico_ia
from app.modules.compras.publico_acceso import ContextoProveedor, acceso_proveedor
from app.modules.core import billing_service
from app.modules.ia.gemini import GeminiError
from app.modules.documentos.models import Documento, EntidadDocumento
from app.modules.presupuestos.models_presupuesto import Presupuesto
from app.modules.presupuestos.presupuesto_calculo import parcial_de, redondear_precio

router = APIRouter(prefix="/api/publico/oferta", tags=["publico"])


class MedicionOfertaOut(BaseModel):
    id: str
    comentario: str | None
    uds: Decimal | None
    longitud: Decimal | None
    anchura: Decimal | None
    altura: Decimal | None
    parcial: Decimal
    orden: int


class DescompuestoOfertaOut(BaseModel):
    id: str
    codigo: str | None
    resumen: str
    unidad: str
    naturaleza: str | None
    rendimiento: Decimal
    factor: Decimal
    precio: Decimal
    importe: Decimal
    orden: int


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
    # Lo que el proveedor ha medido por su cuenta. Si hay parciales, la suma
    # manda sobre `medicion` (que es la del emisor) a la hora de ofertar.
    mediciones: list[MedicionOfertaOut] = Field(default_factory=list)
    medicion_proveedor: Decimal | None
    # Cómo desglosa su precio. Si hay descompuesto, `precio_ofertado` sale de
    # su suma y deja de teclearse a mano.
    descompuesto: list[DescompuestoOfertaOut] = Field(default_factory=list)


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


class MedicionOfertaIn(BaseModel):
    comentario: str | None = Field(default=None, max_length=250)
    uds: Decimal | None = None
    longitud: Decimal | None = None
    anchura: Decimal | None = None
    altura: Decimal | None = None


class DescompuestoOfertaIn(BaseModel):
    codigo: str | None = Field(default=None, max_length=32)
    resumen: str | None = Field(default=None, max_length=250)
    unidad: str | None = Field(default=None, max_length=10)
    naturaleza: str | None = Field(default=None, max_length=32)
    rendimiento: Decimal | None = Field(default=None, ge=0)
    factor: Decimal | None = Field(default=None, ge=0)
    precio: Decimal | None = Field(default=None, ge=0)


class EnviarOfertaOut(BaseModel):
    enviado: bool
    mensaje: str


def _importe_de(componente: OfertaDescompuesto) -> Decimal:
    return redondear_precio(componente.rendimiento * componente.factor * componente.precio)


async def _refrescar_precio(session: AsyncSession, oferta: OfertaLinea) -> None:
    """Con descompuesto, el precio de la línea es la suma de sus componentes —
    igual que una partida con descompuesto propio. Sin él, manda lo que el
    proveedor haya tecleado a mano y aquí no se toca nada."""
    componentes = list(
        (
            await session.execute(
                select(OfertaDescompuesto).where(
                    OfertaDescompuesto.oferta_linea_id == oferta.id
                )
            )
        ).scalars()
    )
    if not componentes:
        return
    oferta.precio_ofertado = sum(
        (_importe_de(c) for c in componentes), Decimal("0.00")
    )


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
                OfertaLinea.id.label("oferta_id"),
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

    # Los parciales de este proveedor, agrupados por línea. Acotados a SUS
    # ofertas, igual que los precios.
    parciales: dict[uuid.UUID, list[MedicionOfertaOut]] = {}
    for medicion in (
        await session.execute(
            select(OfertaMedicion)
            .join(OfertaLinea, OfertaLinea.id == OfertaMedicion.oferta_linea_id)
            .where(OfertaLinea.destinatario_id == ctx.destinatario.id)
            .order_by(OfertaMedicion.orden)
        )
    ).scalars():
        parciales.setdefault(medicion.oferta_linea_id, []).append(
            MedicionOfertaOut(
                id=str(medicion.id),
                comentario=medicion.comentario,
                uds=medicion.uds,
                longitud=medicion.longitud,
                anchura=medicion.anchura,
                altura=medicion.altura,
                parcial=medicion.parcial,
                orden=medicion.orden,
            )
        )

    desgloses: dict[uuid.UUID, list[DescompuestoOfertaOut]] = {}
    for componente in (
        await session.execute(
            select(OfertaDescompuesto)
            .join(OfertaLinea, OfertaLinea.id == OfertaDescompuesto.oferta_linea_id)
            .where(OfertaLinea.destinatario_id == ctx.destinatario.id)
            .order_by(OfertaDescompuesto.orden)
        )
    ).scalars():
        desgloses.setdefault(componente.oferta_linea_id, []).append(
            DescompuestoOfertaOut(
                id=str(componente.id),
                codigo=componente.codigo,
                resumen=componente.resumen,
                unidad=componente.unidad,
                naturaleza=componente.naturaleza,
                rendimiento=componente.rendimiento,
                factor=componente.factor,
                precio=componente.precio,
                importe=_importe_de(componente),
                orden=componente.orden,
            )
        )

    return [
        LineaSeparataOut(
            id=str(f.id),
            descompuesto=desgloses.get(f.oferta_id, []),
            capitulo_resumen=f.capitulo_resumen,
            codigo=f.codigo,
            resumen=f.resumen,
            # Saneado también a la SALIDA, no solo al guardarlo: esta página
            # es la única sin sesión, y el texto viene de un editor
            # enriquecido. Volver a pasarlo por la lista blanca cuesta nada y
            # cubre cualquier fila anterior al saneado de entrada.
            texto=sanear_html(f.texto),
            unidad=f.unidad,
            medicion=f.medicion,
            mediciones=parciales.get(f.oferta_id, []),
            medicion_proveedor=(
                sum((m.parcial for m in parciales[f.oferta_id]), Decimal("0"))
                if f.oferta_id in parciales
                else None
            ),
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


# --- Estado de mediciones del proveedor ---


async def _oferta_de_linea(
    session: AsyncSession, ctx: ContextoProveedor, linea_id: str
) -> OfertaLinea:
    """La fila de oferta de ESTE proveedor para esa línea, creándola si aún no
    existe. Acota siempre por destinatario y por paquete: los ids vienen del
    cliente y no valen por sí solos."""
    try:
        uuid_linea = uuid.UUID(linea_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Línea no válida."
        ) from None

    linea = await session.scalar(
        select(SolicitudLinea).where(
            SolicitudLinea.id == uuid_linea,
            SolicitudLinea.solicitud_id == ctx.solicitud.id,
        )
    )
    if linea is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Esa línea no pertenece a esta solicitud.",
        )

    oferta = await session.scalar(
        select(OfertaLinea).where(
            OfertaLinea.linea_id == linea.id,
            OfertaLinea.destinatario_id == ctx.destinatario.id,
        )
    )
    if oferta is None:
        oferta = OfertaLinea(
            organization_id=ctx.organization_id,
            destinatario_id=ctx.destinatario.id,
            linea_id=linea.id,
        )
        session.add(oferta)
        await session.flush()
    return oferta


async def _medicion_propia(
    session: AsyncSession, ctx: ContextoProveedor, medicion_id: uuid.UUID
) -> OfertaMedicion:
    """Un parcial, verificando que es de ESTE proveedor. RLS solo acota la
    organización, y dentro de ella conviven los parciales de todos los
    proveedores del paquete."""
    fila = (
        await session.execute(
            select(OfertaMedicion)
            .join(OfertaLinea, OfertaLinea.id == OfertaMedicion.oferta_linea_id)
            .where(
                OfertaMedicion.id == medicion_id,
                OfertaLinea.destinatario_id == ctx.destinatario.id,
            )
        )
    ).scalar_one_or_none()
    if fila is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medición no encontrada")
    return fila


def _recalcular(medicion: OfertaMedicion) -> None:
    medicion.parcial = parcial_de(
        medicion.uds, medicion.longitud, medicion.anchura, medicion.altura
    )


@router.post("/{token}/lineas/{linea_id}/mediciones", response_model=SeparataOut)
async def anadir_medicion(
    linea_id: str,
    datos: MedicionOfertaIn,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    """Un parcial más al estado de mediciones que aporta el proveedor."""
    oferta = await _oferta_de_linea(session, ctx, linea_id)
    ultimo = await session.scalar(
        select(func.coalesce(func.max(OfertaMedicion.orden), -1)).where(
            OfertaMedicion.oferta_linea_id == oferta.id
        )
    )
    medicion = OfertaMedicion(
        organization_id=ctx.organization_id,
        oferta_linea_id=oferta.id,
        comentario=datos.comentario,
        uds=datos.uds,
        longitud=datos.longitud,
        anchura=datos.anchura,
        altura=datos.altura,
        orden=(-1 if ultimo is None else ultimo) + 1,
    )
    _recalcular(medicion)
    session.add(medicion)
    await session.flush()
    return await _separata(session, ctx)


@router.patch("/{token}/mediciones/{medicion_id}", response_model=SeparataOut)
async def editar_medicion(
    medicion_id: uuid.UUID,
    datos: MedicionOfertaIn,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    """Solo toca los campos que vengan en el cuerpo. Es importante que sea un
    PATCH de verdad y no un reemplazo: la separata edita campo a campo al
    salir de cada casilla, y con un reemplazo dos ediciones seguidas podrían
    pisarse con los valores viejos que tuviera la pantalla."""
    medicion = await _medicion_propia(session, ctx, medicion_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(medicion, campo, valor)
    _recalcular(medicion)
    await session.flush()
    return await _separata(session, ctx)


@router.delete("/{token}/mediciones/{medicion_id}", response_model=SeparataOut)
async def eliminar_medicion(
    medicion_id: uuid.UUID,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    medicion = await _medicion_propia(session, ctx, medicion_id)
    await session.delete(medicion)
    await session.flush()
    return await _separata(session, ctx)


# --- Descompuesto del proveedor ---


async def _componente_propio(
    session: AsyncSession, ctx: ContextoProveedor, componente_id: uuid.UUID
) -> OfertaDescompuesto:
    """Un componente, verificando que es de ESTE proveedor: RLS solo acota la
    organización, y dentro conviven los desgloses de todos los del paquete."""
    fila = (
        await session.execute(
            select(OfertaDescompuesto)
            .join(OfertaLinea, OfertaLinea.id == OfertaDescompuesto.oferta_linea_id)
            .where(
                OfertaDescompuesto.id == componente_id,
                OfertaLinea.destinatario_id == ctx.destinatario.id,
            )
        )
    ).scalar_one_or_none()
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado"
        )
    return fila


@router.post("/{token}/lineas/{linea_id}/descompuesto", response_model=SeparataOut)
async def anadir_componente(
    linea_id: str,
    datos: DescompuestoOfertaIn,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    oferta = await _oferta_de_linea(session, ctx, linea_id)
    ultimo = await session.scalar(
        select(func.coalesce(func.max(OfertaDescompuesto.orden), -1)).where(
            OfertaDescompuesto.oferta_linea_id == oferta.id
        )
    )
    componente = OfertaDescompuesto(
        organization_id=ctx.organization_id,
        oferta_linea_id=oferta.id,
        codigo=datos.codigo,
        resumen=datos.resumen or "",
        unidad=datos.unidad or "ud",
        naturaleza=datos.naturaleza,
        rendimiento=datos.rendimiento if datos.rendimiento is not None else Decimal("1"),
        factor=datos.factor if datos.factor is not None else Decimal("1"),
        precio=datos.precio if datos.precio is not None else Decimal("0.00"),
        orden=(-1 if ultimo is None else ultimo) + 1,
    )
    session.add(componente)
    await session.flush()
    await _refrescar_precio(session, oferta)
    await session.flush()
    return await _separata(session, ctx)


@router.patch("/{token}/descompuesto/{componente_id}", response_model=SeparataOut)
async def editar_componente(
    componente_id: uuid.UUID,
    datos: DescompuestoOfertaIn,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    """PATCH de verdad: solo toca lo que venga en el cuerpo, para que editar
    campo a campo no pise lo recién guardado (mismo motivo que en las
    mediciones)."""
    componente = await _componente_propio(session, ctx, componente_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is None and campo in ("resumen", "unidad", "rendimiento", "factor", "precio"):
            continue
        setattr(componente, campo, valor)
    await session.flush()

    oferta = await session.get(OfertaLinea, componente.oferta_linea_id)
    if oferta is not None:
        await _refrescar_precio(session, oferta)
    await session.flush()
    return await _separata(session, ctx)


@router.delete("/{token}/descompuesto/{componente_id}", response_model=SeparataOut)
async def eliminar_componente(
    componente_id: uuid.UUID,
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> SeparataOut:
    componente = await _componente_propio(session, ctx, componente_id)
    oferta_id = componente.oferta_linea_id
    await session.delete(componente)
    await session.flush()

    oferta = await session.get(OfertaLinea, oferta_id)
    if oferta is not None:
        await _refrescar_precio(session, oferta)
    await session.flush()
    return await _separata(session, ctx)


# --- Lectura del documento del proveedor con IA ---

# Tope por enlace: el endpoint es público y cada lectura la paga el emisor.
MAX_USOS_IA = 10


class LecturaIAOut(BaseModel):
    rellenadas: int
    mensaje: str
    separata: SeparataOut


@router.post("/{token}/ia/documento", response_model=LecturaIAOut)
async def leer_documento_con_ia(
    fichero: UploadFile = File(...),
    ctx: ContextoProveedor = Depends(acceso_proveedor),
    session: AsyncSession = Depends(get_session),
) -> LecturaIAOut:
    """El proveedor sube su hoja de precios y la IA rellena lo que reconozca.

    Lo paga el EMISOR: el contexto público está fijado a su organización, así
    que el consumo se registra ahí por construcción. Por eso hay tope por
    enlace — si no, cualquiera con el enlace podría gastarle los créditos."""
    if ctx.estado.usos_ia >= MAX_USOS_IA:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Se ha alcanzado el límite de lecturas automáticas de este enlace. "
            "Rellena los precios a mano o pídele otro enlace a quien te lo mandó.",
        )

    tipo = fichero.content_type or "application/octet-stream"
    if tipo not in publico_ia.MIME_ACEPTADOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Formato no admitido: sube un PDF, un Excel o un CSV.",
        )

    # Por trozos y con tope: leer entero un fichero sin límite en un endpoint
    # público es una denegación de servicio con una sola petición.
    trozos: list[bytes] = []
    total = 0
    while trozo := await fichero.read(64 * 1024):
        total += len(trozo)
        if total > publico_ia.MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="El documento es demasiado grande (máximo 8 MB).",
            )
        trozos.append(trozo)
    contenido = b"".join(trozos)
    if not contenido:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El documento está vacío."
        )

    lineas = await _lineas(session, ctx)
    resumen_lineas = [
        {"id": l.id, "resumen": l.resumen, "unidad": l.unidad, "medicion": str(l.medicion)}
        for l in lineas
    ]

    try:
        precios, uso = await publico_ia.leer_precios(
            session,
            contenido=contenido,
            mime_type=tipo,
            nombre=fichero.filename or "documento",
            lineas=resumen_lineas,
        )
    except GeminiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    escritas = 0
    saltadas = 0
    for id_linea, precio in precios.items():
        oferta = await _oferta_de_linea(session, ctx, id_linea)
        # No se pisa un desglose ya hecho: ahí el precio sale de la suma.
        tiene_desglose = await session.scalar(
            select(func.count(OfertaDescompuesto.id)).where(
                OfertaDescompuesto.oferta_linea_id == oferta.id
            )
        )
        if tiene_desglose:
            saltadas += 1
            continue
        oferta.precio_ofertado = precio
        escritas += 1

    ctx.estado.usos_ia += 1
    await billing_service.registrar_uso_ia(
        session,
        organization_id=ctx.organization_id,
        usuario_subject=f"proveedor:{ctx.destinatario.id}",
        usuario_nombre="Proveedor (enlace externo)",
        proveedor="gemini",
        modelo=uso.modelo,
        tokens_entrada=uso.tokens_entrada,
        tokens_salida=uso.tokens_salida,
        referencia=str(ctx.solicitud.id),
    )
    await session.flush()

    if escritas:
        mensaje = (
            f"Se han rellenado {escritas} precio{'s' if escritas != 1 else ''}. "
            "Revísalos antes de enviar."
        )
    elif saltadas:
        mensaje = (
            "No se ha cambiado nada: esas líneas ya tienen desglose, y ahí el precio "
            "sale de la suma de sus componentes."
        )
    else:
        mensaje = "No he sabido sacar ningún precio del documento. Rellénalos a mano."
    if escritas and saltadas:
        mensaje += (
            f" Otras {saltadas} se han dejado como estaban, por tener desglose propio."
            if saltadas != 1
            else " Otra se ha dejado como estaba, por tener desglose propio."
        )

    return LecturaIAOut(
        rellenadas=escritas,
        mensaje=mensaje,
        separata=await _separata(session, ctx),
    )


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
