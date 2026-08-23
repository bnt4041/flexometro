import re
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import TIPO_IVA_PORCENTAJE
from app.core.numeracion import siguiente_referencia
from app.core.redondeo import redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.facturacion.models import (
    Certificacion,
    CertificacionLinea,
    Cobro,
    EstadoCertificacion,
    EstadoFactura,
    Factura,
)
from app.modules.facturacion.schemas import (
    CertificacionCreate,
    CertificacionUpdate,
    CobroCreate,
    FacturaSuelta,
    FacturaUpdate,
    GenerarDesdeCertificacion,
)

PREFIJO_CERT = "CERT"
_RE_CERT = re.compile(rf"^{PREFIJO_CERT}(\d+)$")


class CodigoDuplicado(Exception):
    pass


class ObraInvalida(Exception):
    pass


class PartidaInvalida(Exception):
    pass


class CertificacionBloqueada(Exception):
    pass


class CertificacionInvalida(Exception):
    pass


class FacturaNoEditable(Exception):
    pass


# --- Códigos internos ---


async def _siguiente(session: AsyncSession, modelo, prefijo: str, patron: re.Pattern) -> str:
    org_id = require_organization_id()
    codigos = await session.execute(
        select(modelo.codigo).where(modelo.organization_id == org_id)
    )
    maximo = 0
    for (codigo,) in codigos.all():
        encaje = patron.match(codigo)
        if encaje:
            maximo = max(maximo, int(encaje.group(1)))
    return f"{prefijo}{maximo + 1:05d}"


async def siguiente_codigo_certificacion(session: AsyncSession) -> str:
    return await _siguiente(session, Certificacion, PREFIJO_CERT, _RE_CERT)


async def siguiente_codigo_factura(session: AsyncSession) -> str:
    """Fase 16: patrón configurable por cuenta (Administración → ficha de
    cuenta → Numeración), en vez del prefijo "FAC" fijo de antes. Es el
    `codigo` interno de la factura, NUNCA `serie`/`numero` (la numeración
    fiscal, ver el docstring de `Factura` en `models.py`)."""
    org_id = require_organization_id()
    return await siguiente_referencia(session, organization_id=org_id, tipo_documento="factura")


# --- Certificaciones ---


async def _siguiente_numero_certificacion(session: AsyncSession, obra_id: uuid.UUID) -> int:
    maximo = await session.scalar(
        select(func.max(Certificacion.numero)).where(Certificacion.obra_id == obra_id)
    )
    return int(maximo or 0) + 1


async def _medicion_anterior(
    session: AsyncSession, obra_id: uuid.UUID, partida_id: uuid.UUID
) -> Decimal:
    """Última medición acumulada certificada para esta partida en esta obra.

    0 si nunca se ha certificado. Se mira la certificación de mayor número,
    con independencia de si está emitida o sigue en borrador: dos borradores
    a la vez sobre la misma partida no tendrían sentido, pero si ocurriera, se
    encadena igualmente sobre el último.
    """
    fila = await session.execute(
        select(CertificacionLinea.medicion_actual)
        .join(Certificacion, Certificacion.id == CertificacionLinea.certificacion_id)
        .where(
            Certificacion.obra_id == obra_id,
            CertificacionLinea.partida_id == partida_id,
        )
        .order_by(Certificacion.numero.desc())
        .limit(1)
    )
    valor = fila.scalar_one_or_none()
    return valor if valor is not None else Decimal("0.000")


async def listar_certificaciones(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Certificacion], int]:
    org_id = require_organization_id()
    base = select(Certificacion).where(Certificacion.organization_id == org_id)
    if obra_id is not None:
        base = base.where(Certificacion.obra_id == obra_id)
    if creado_por_subject is not None:
        base = base.where(Certificacion.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    filas = await session.execute(
        base.order_by(Certificacion.obra_id, Certificacion.numero.desc()).limit(limit).offset(offset)
    )
    return list(filas.scalars()), int(total or 0)


async def obtener_certificacion(
    session: AsyncSession, certificacion_id: uuid.UUID
) -> Certificacion | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Certificacion)
        .options(selectinload(Certificacion.lineas))
        .where(Certificacion.id == certificacion_id, Certificacion.organization_id == org_id)
    )


async def crear_certificacion(
    session: AsyncSession, datos: CertificacionCreate
) -> Certificacion:
    from app.modules.obras.service import obtener_obra
    from app.modules.presupuestos.models_presupuesto import Partida

    org_id = require_organization_id()
    obra = await obtener_obra(session, datos.obra_id)
    if obra is None:
        raise ObraInvalida("La obra no existe en esta organización")

    codigo = await siguiente_codigo_certificacion(session)
    numero = await _siguiente_numero_certificacion(session, datos.obra_id)

    certificacion = Certificacion(
        organization_id=org_id,
        codigo=codigo,
        numero=numero,
        obra_id=datos.obra_id,
        fecha=datos.fecha,
        retencion_garantia_pct=datos.retencion_garantia_pct,
        notas=datos.notas,
        **datos_autoria(),
    )
    session.add(certificacion)
    await session.flush()

    for orden, linea in enumerate(datos.lineas):
        partida = await session.scalar(
            select(Partida).where(
                Partida.id == linea.partida_id, Partida.organization_id == org_id
            )
        )
        if partida is None or partida.presupuesto_id != obra.presupuesto_id:
            raise PartidaInvalida(
                "La partida indicada no pertenece al presupuesto de esta obra"
            )

        anterior = await _medicion_anterior(session, datos.obra_id, linea.partida_id)
        if linea.medicion_actual < anterior:
            raise CertificacionInvalida(
                f"'{partida.codigo}': la medición certificada ({linea.medicion_actual}) no "
                f"puede ser menor que la ya certificada ({anterior})"
            )

        periodo = linea.medicion_actual - anterior
        session.add(
            CertificacionLinea(
                organization_id=org_id,
                certificacion_id=certificacion.id,
                partida_id=partida.id,
                codigo=partida.codigo,
                resumen=partida.resumen,
                unidad=partida.unidad,
                precio=partida.precio,
                medicion_anterior=anterior,
                medicion_actual=linea.medicion_actual,
                medicion_periodo=periodo,
                importe_periodo=redondear_precio(periodo * partida.precio),
                orden=orden,
            )
        )

    await session.flush()
    await session.refresh(certificacion, attribute_names=["lineas"])
    return certificacion


async def actualizar_certificacion(
    session: AsyncSession, certificacion_id: uuid.UUID, datos: CertificacionUpdate
) -> Certificacion | None:
    certificacion = await obtener_certificacion(session, certificacion_id)
    if certificacion is None:
        return None
    if certificacion.estado != EstadoCertificacion.BORRADOR:
        raise CertificacionBloqueada("Una certificación emitida ya no se puede editar")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(certificacion, campo, valor)
    await session.flush()
    return certificacion


async def emitir_certificacion(
    session: AsyncSession, certificacion_id: uuid.UUID
) -> Certificacion | None:
    certificacion = await obtener_certificacion(session, certificacion_id)
    if certificacion is None:
        return None
    certificacion.estado = EstadoCertificacion.EMITIDA
    await session.flush()
    return certificacion


async def eliminar_certificacion(session: AsyncSession, certificacion_id: uuid.UUID) -> bool:
    certificacion = await obtener_certificacion(session, certificacion_id)
    if certificacion is None:
        return False
    if certificacion.estado != EstadoCertificacion.BORRADOR:
        raise CertificacionBloqueada(
            "No se puede eliminar una certificación emitida; genera una negativa si hace "
            "falta corregirla"
        )
    await session.delete(certificacion)
    await session.flush()
    return True


def importes_certificacion(certificacion: Certificacion) -> dict[str, Decimal]:
    ejecutado = redondear_precio(
        sum((l.importe_periodo for l in certificacion.lineas), Decimal("0.00"))
    )
    retenido = redondear_precio(
        ejecutado * certificacion.retencion_garantia_pct / Decimal("100")
    )
    return {
        "importe_ejecutado": ejecutado,
        "importe_retenido": retenido,
        "importe_liquido": redondear_precio(ejecutado - retenido),
    }


async def certificacion_facturada(session: AsyncSession, certificacion_id: uuid.UUID) -> bool:
    org_id = require_organization_id()
    existe = await session.scalar(
        select(Factura.id).where(
            Factura.certificacion_id == certificacion_id,
            Factura.organization_id == org_id,
            Factura.estado != EstadoFactura.ANULADA,
        )
    )
    return existe is not None


# --- Facturas ---


async def _datos_obra(session: AsyncSession, obra_id: uuid.UUID):
    from app.modules.obras.service import obtener_obra
    from app.modules.presupuestos.presupuesto_service import obtener as obtener_presupuesto

    obra = await obtener_obra(session, obra_id)
    if obra is None:
        raise ObraInvalida("La obra no existe en esta organización")
    presupuesto = await obtener_presupuesto(session, obra.presupuesto_id)
    return obra, presupuesto


def _calcular_iva(base: Decimal, tipo_iva, isp: bool) -> Decimal:
    if isp:
        return Decimal("0.00")
    porcentaje = Decimal(TIPO_IVA_PORCENTAJE[tipo_iva])
    return redondear_precio(base * porcentaje / Decimal("100"))


async def crear_factura_suelta(session: AsyncSession, datos: FacturaSuelta) -> Factura:
    org_id = require_organization_id()
    obra, presupuesto = await _datos_obra(session, datos.obra_id)

    cliente_id = datos.cliente_id or (presupuesto.cliente_id if presupuesto else None)
    if cliente_id is None:
        raise ObraInvalida(
            "La obra no tiene cliente en su presupuesto; indica el cliente a mano"
        )

    cuota_iva = _calcular_iva(datos.base_imponible, datos.tipo_iva, datos.inversion_sujeto_pasivo)
    factura = Factura(
        organization_id=org_id,
        codigo=await siguiente_codigo_factura(session),
        serie=datos.serie or str(date.today().year),
        numero=None,
        obra_id=datos.obra_id,
        certificacion_id=None,
        cliente_id=cliente_id,
        concepto=datos.concepto,
        fecha_vencimiento=datos.fecha_vencimiento,
        base_imponible=redondear_precio(datos.base_imponible),
        tipo_iva=datos.tipo_iva,
        inversion_sujeto_pasivo=datos.inversion_sujeto_pasivo,
        cuota_iva=cuota_iva,
        total=redondear_precio(datos.base_imponible + cuota_iva),
        notas=datos.notas,
        **datos_autoria(),
    )
    session.add(factura)
    await session.flush()
    return factura


async def generar_factura_desde_certificacion(
    session: AsyncSession, certificacion_id: uuid.UUID, datos: GenerarDesdeCertificacion
) -> Factura | None:
    certificacion = await obtener_certificacion(session, certificacion_id)
    if certificacion is None:
        return None
    if certificacion.estado != EstadoCertificacion.EMITIDA:
        raise CertificacionBloqueada(
            "Solo se puede facturar una certificación ya emitida: una en borrador "
            "todavía puede cambiar de importe"
        )
    if await certificacion_facturada(session, certificacion_id):
        raise CertificacionBloqueada("Esta certificación ya tiene una factura activa")

    org_id = require_organization_id()
    obra, presupuesto = await _datos_obra(session, certificacion.obra_id)
    if presupuesto is None or presupuesto.cliente_id is None:
        raise ObraInvalida("El presupuesto de la obra no tiene cliente asignado")

    importes = importes_certificacion(certificacion)
    tipo_iva = presupuesto.tipo_iva
    isp = presupuesto.inversion_sujeto_pasivo
    cuota_iva = _calcular_iva(importes["importe_liquido"], tipo_iva, isp)

    factura = Factura(
        organization_id=org_id,
        codigo=await siguiente_codigo_factura(session),
        serie=datos.serie or str(date.today().year),
        numero=None,
        obra_id=certificacion.obra_id,
        certificacion_id=certificacion.id,
        cliente_id=presupuesto.cliente_id,
        concepto=datos.concepto or f"Certificación nº {certificacion.numero} — {obra.nombre}",
        fecha_vencimiento=datos.fecha_vencimiento,
        base_imponible=importes["importe_liquido"],
        tipo_iva=tipo_iva,
        inversion_sujeto_pasivo=isp,
        cuota_iva=cuota_iva,
        total=redondear_precio(importes["importe_liquido"] + cuota_iva),
        notas=datos.notas,
        **datos_autoria(),
    )
    session.add(factura)
    await session.flush()
    return factura


async def listar_facturas(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    estado: str | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[tuple[Factura, str]], int]:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    base = (
        select(Factura, Tercero.razon_social)
        .join(Tercero, Tercero.id == Factura.cliente_id)
        # situacion_cobro() recorre factura.cobros; sin precargarlo aquí,
        # accederlo dispararía una carga perezosa fuera del contexto async
        # (MissingGreenlet) al construir cada fila del listado.
        .options(selectinload(Factura.cobros))
        .where(Factura.organization_id == org_id)
    )
    if obra_id is not None:
        base = base.where(Factura.obra_id == obra_id)
    if estado:
        base = base.where(Factura.estado == estado)
    if creado_por_subject is not None:
        base = base.where(Factura.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.with_only_columns(Factura.id).order_by(None).subquery())
    )
    filas = await session.execute(
        base.order_by(Factura.serie.desc(), Factura.numero.desc().nulls_first())
        .limit(limit)
        .offset(offset)
    )
    return list(filas.all()), int(total or 0)


async def obtener_factura(
    session: AsyncSession, factura_id: uuid.UUID
) -> tuple[Factura, str] | None:
    from app.modules.terceros.models import Tercero

    org_id = require_organization_id()
    fila = (
        await session.execute(
            select(Factura, Tercero.razon_social)
            .join(Tercero, Tercero.id == Factura.cliente_id)
            .options(selectinload(Factura.cobros))
            .where(Factura.id == factura_id, Factura.organization_id == org_id)
        )
    ).first()
    return tuple(fila) if fila else None


async def obtener_factura_obj(session: AsyncSession, factura_id: uuid.UUID) -> Factura | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Factura).where(Factura.id == factura_id, Factura.organization_id == org_id)
    )


async def actualizar_factura(
    session: AsyncSession, factura_id: uuid.UUID, datos: FacturaUpdate
) -> Factura | None:
    factura = await obtener_factura_obj(session, factura_id)
    if factura is None:
        return None
    if factura.estado != EstadoFactura.BORRADOR:
        raise FacturaNoEditable("Una factura emitida no se puede editar, solo anular")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(factura, campo, valor)
    await session.flush()
    return factura


async def eliminar_factura(session: AsyncSession, factura_id: uuid.UUID) -> bool:
    factura = await obtener_factura_obj(session, factura_id)
    if factura is None:
        return False
    if factura.estado != EstadoFactura.BORRADOR:
        raise FacturaNoEditable(
            "Una factura emitida no se borra nunca, para no dejar huecos en la "
            "numeración; anúlala en su lugar"
        )
    await session.delete(factura)
    await session.flush()
    return True


async def emitir_factura(session: AsyncSession, factura_id: uuid.UUID) -> Factura | None:
    """Asigna el número fiscal y fija la fecha de emisión.

    El número se consume aquí, no al crear el borrador: descartar un borrador
    nunca deja un hueco en la serie.
    """
    org_id = require_organization_id()
    factura = await obtener_factura_obj(session, factura_id)
    if factura is None:
        return None
    if factura.estado != EstadoFactura.BORRADOR:
        raise FacturaNoEditable("Esta factura ya está emitida o anulada")

    maximo = await session.scalar(
        select(func.max(Factura.numero)).where(
            Factura.organization_id == org_id, Factura.serie == factura.serie
        )
    )
    factura.numero = int(maximo or 0) + 1
    factura.fecha_emision = date.today()
    factura.estado = EstadoFactura.EMITIDA
    await session.flush()
    return factura


async def anular_factura(
    session: AsyncSession, factura_id: uuid.UUID, motivo: str
) -> Factura | None:
    factura = await obtener_factura_obj(session, factura_id)
    if factura is None:
        return None
    if factura.estado == EstadoFactura.ANULADA:
        raise FacturaNoEditable("Esta factura ya está anulada")
    factura.estado = EstadoFactura.ANULADA
    factura.motivo_anulacion = motivo
    await session.flush()
    return factura


def situacion_cobro(factura: Factura) -> tuple[Decimal, Decimal, str, bool]:
    """(cobrado, pendiente, situación, vencida). No se almacena: se deriva de
    los cobros registrados, para que nunca se pueda desincronizar."""
    cobrado = redondear_precio(sum((c.importe for c in factura.cobros), Decimal("0.00")))
    pendiente = redondear_precio(factura.total - cobrado)

    if factura.estado != EstadoFactura.EMITIDA:
        situacion = "-"
    elif pendiente <= Decimal("0.00"):
        situacion = "cobrada"
    elif cobrado > Decimal("0.00"):
        situacion = "parcial"
    else:
        situacion = "pendiente"

    vencida = (
        factura.estado == EstadoFactura.EMITIDA
        and situacion != "cobrada"
        and factura.fecha_vencimiento is not None
        and factura.fecha_vencimiento < date.today()
    )
    return cobrado, pendiente, situacion, vencida


async def registrar_cobro(
    session: AsyncSession, factura_id: uuid.UUID, datos: CobroCreate
) -> Cobro | None:
    org_id = require_organization_id()
    factura = await session.scalar(
        select(Factura)
        .options(selectinload(Factura.cobros))
        .where(Factura.id == factura_id, Factura.organization_id == org_id)
    )
    if factura is None:
        return None
    if factura.estado != EstadoFactura.EMITIDA:
        raise FacturaNoEditable("Solo se registran cobros de facturas emitidas")

    # La comprobación de una FK la hace PostgreSQL saltándose RLS, así que
    # sin esto un id de la cuenta bancaria de la otra empresa colaría: el
    # cobro quedaría apuntando a una cuenta que su propia organización no
    # puede ni ver.
    if datos.cuenta_financiera_id is not None:
        from app.modules.core.tesoreria_models import CuentaFinanciera

        propia = await session.scalar(
            select(CuentaFinanciera.id).where(
                CuentaFinanciera.id == datos.cuenta_financiera_id,
                CuentaFinanciera.organization_id == org_id,
            )
        )
        if propia is None:
            raise FacturaNoEditable("La cuenta de banco o caja indicada no es de esta empresa")

    cobro = Cobro(organization_id=org_id, factura_id=factura_id, **datos.model_dump())
    session.add(cobro)
    await session.flush()
    return cobro


async def obtener_cobro(session: AsyncSession, cobro_id: uuid.UUID) -> Cobro | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Cobro).where(Cobro.id == cobro_id, Cobro.organization_id == org_id)
    )


async def eliminar_cobro(session: AsyncSession, cobro_id: uuid.UUID) -> bool:
    cobro = await obtener_cobro(session, cobro_id)
    if cobro is None:
        return False
    await session.delete(cobro)
    await session.flush()
    return True
