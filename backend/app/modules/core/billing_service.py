"""Tarifas, descuentos y coste estimado de cada cuenta.

Ninguna de estas tablas lleva RLS: solo las toca el rol superadmin a través
de este servicio, nunca un endpoint de negocio de una organización propia —
a diferencia de `organization_module` (que sí toca Ajustes, una pantalla de
cualquier usuario normal), estas son puramente administrativas, igual que
`core.organization`/`core.cuenta`.

Desde la Fase 14, la facturación SaaS (tarifa asignada, cobros, uso de IA,
descuentos, coste estimado) es por CUENTA, no por organización: varias
organizaciones de la misma cuenta comparten un único contrato consolidado.
`UsoIA` sigue registrándose por organización (auditoría de quién/qué
organización consumió qué), pero el coste se agrega sumando todas las
organizaciones de la cuenta — ver `modulos_activos_de_cuenta` y
`tokens_del_mes_de_cuenta`.
"""

import uuid
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import fijar_organizacion_activa
from app.core.redondeo import redondear_precio
from app.modules.core import service as core_service
from app.modules.core.billing_models import (
    CobroSaas,
    CuentaDescuento,
    Descuento,
    Tarifa,
    TarifaModulo,
    TipoDescuento,
    UsoIA,
)
from app.modules.core.billing_schemas import (
    DescuentoCreate,
    DescuentoUpdate,
    TarifaCreate,
    TarifaUpdate,
)
from app.modules.core.cuenta_service import organizaciones_de_cuenta


class NombreDuplicado(Exception):
    pass


class DescuentoInvalido(Exception):
    pass


class DescuentoNoEncontrado(Exception):
    pass


class AplicacionYaVigente(Exception):
    pass


class AplicacionNoEncontrada(Exception):
    pass


# --- Tarifas ---


async def listar_tarifas(session: AsyncSession) -> list[Tarifa]:
    filas = await session.execute(
        select(Tarifa).options(selectinload(Tarifa.modulos)).order_by(Tarifa.nombre)
    )
    return list(filas.scalars().unique())


async def obtener_tarifa(session: AsyncSession, tarifa_id: uuid.UUID) -> Tarifa | None:
    return await session.scalar(
        select(Tarifa).options(selectinload(Tarifa.modulos)).where(Tarifa.id == tarifa_id)
    )


async def crear_tarifa(session: AsyncSession, datos: TarifaCreate) -> Tarifa:
    existe = await session.scalar(select(Tarifa.id).where(Tarifa.nombre == datos.nombre))
    if existe:
        raise NombreDuplicado(f"Ya existe una tarifa con el nombre '{datos.nombre}'")

    tarifa = Tarifa(
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        precio_1000_tokens_deepseek=datos.precio_1000_tokens_deepseek,
        precio_1000_tokens_gemini=datos.precio_1000_tokens_gemini,
    )
    session.add(tarifa)
    await session.flush()
    for modulo in datos.modulos:
        session.add(
            TarifaModulo(
                tarifa_id=tarifa.id,
                module_code=modulo.module_code,
                precio_mensual=modulo.precio_mensual,
            )
        )
    await session.flush()
    await session.refresh(tarifa, attribute_names=["modulos"])
    return tarifa


async def actualizar_tarifa(
    session: AsyncSession, tarifa_id: uuid.UUID, datos: TarifaUpdate
) -> Tarifa | None:
    tarifa = await obtener_tarifa(session, tarifa_id)
    if tarifa is None:
        return None

    cambios = datos.model_dump(exclude_unset=True, exclude={"modulos"})
    for campo, valor in cambios.items():
        setattr(tarifa, campo, valor)

    if datos.modulos is not None:
        for modulo in list(tarifa.modulos):
            await session.delete(modulo)
        await session.flush()
        for modulo in datos.modulos:
            session.add(
                TarifaModulo(
                    tarifa_id=tarifa.id,
                    module_code=modulo.module_code,
                    precio_mensual=modulo.precio_mensual,
                )
            )

    await session.flush()
    await session.refresh(tarifa, attribute_names=["modulos"])
    return tarifa


# --- Descuentos: catálogo ---
#
# El descuento se crea una vez, en la zona de Tarifas, y desde ahí se puede
# aplicar a cualquier cuenta (ver más abajo). Nada en este bloque toca
# `CuentaDescuento`: crear/editar/borrar el catálogo es independiente de
# quién lo tenga aplicado.


async def listar_descuentos(
    session: AsyncSession, *, tarifa_id: uuid.UUID | None = None
) -> list[Descuento]:
    base = select(Descuento)
    if tarifa_id is not None:
        base = base.where(Descuento.tarifa_id == tarifa_id)
    filas = await session.execute(base.order_by(Descuento.created_at.desc()))
    return list(filas.scalars())


async def crear_descuento(session: AsyncSession, datos: DescuentoCreate) -> Descuento:
    if datos.tipo == TipoDescuento.PORCENTAJE and datos.valor > 100:
        raise DescuentoInvalido("Un descuento porcentual no puede superar el 100 %")

    descuento = Descuento(**datos.model_dump())
    session.add(descuento)
    await session.flush()
    return descuento


async def actualizar_descuento(
    session: AsyncSession, descuento_id: uuid.UUID, datos: DescuentoUpdate
) -> Descuento | None:
    descuento = await session.get(Descuento, descuento_id)
    if descuento is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(descuento, campo, valor)
    await session.flush()
    return descuento


async def eliminar_descuento(session: AsyncSession, descuento_id: uuid.UUID) -> bool:
    descuento = await session.get(Descuento, descuento_id)
    if descuento is None:
        return False
    await session.delete(descuento)
    await session.flush()
    return True


# --- Descuentos: aplicación a una cuenta ---
#
# Aplicar y anular son las únicas acciones que tocan `CuentaDescuento`. Cada
# aplicación es un hecho histórico propio: anular no borra la fila
# (`anulado_en` pasa de NULL a la fecha), y volver a aplicar el mismo
# descuento tras anularlo crea una fila nueva — así el histórico completo de
# una cuenta queda intacto, no se pisa.


async def listar_aplicaciones(
    session: AsyncSession, cuenta_id: uuid.UUID
) -> list[CuentaDescuento]:
    filas = await session.execute(
        select(CuentaDescuento)
        .options(selectinload(CuentaDescuento.descuento))
        .where(CuentaDescuento.cuenta_id == cuenta_id)
        .order_by(CuentaDescuento.aplicado_en.desc())
    )
    return list(filas.scalars())


async def aplicar_descuentos(
    session: AsyncSession, cuenta_id: uuid.UUID, descuento_ids: list[uuid.UUID]
) -> list[CuentaDescuento]:
    vigentes = await session.execute(
        select(CuentaDescuento.descuento_id).where(
            CuentaDescuento.cuenta_id == cuenta_id,
            CuentaDescuento.anulado_en.is_(None),
        )
    )
    ya_vigentes = {fila[0] for fila in vigentes.all()}

    creadas: list[CuentaDescuento] = []
    for descuento_id in descuento_ids:
        if descuento_id in ya_vigentes:
            raise AplicacionYaVigente(
                "Alguno de los descuentos seleccionados ya está vigente en esta cuenta"
            )
        descuento = await session.get(Descuento, descuento_id)
        if descuento is None:
            raise DescuentoNoEncontrado(f"El descuento {descuento_id} no existe")
        aplicacion = CuentaDescuento(cuenta_id=cuenta_id, descuento_id=descuento_id)
        session.add(aplicacion)
        creadas.append(aplicacion)

    await session.flush()
    for aplicacion in creadas:
        await session.refresh(aplicacion, attribute_names=["descuento"])
    return creadas


async def anular_aplicacion(session: AsyncSession, aplicacion_id: uuid.UUID) -> CuentaDescuento:
    aplicacion = await session.get(
        CuentaDescuento, aplicacion_id, options=[selectinload(CuentaDescuento.descuento)]
    )
    if aplicacion is None:
        raise AplicacionNoEncontrada("La aplicación de descuento no existe")
    if aplicacion.anulado_en is None:
        aplicacion.anulado_en = datetime.now(UTC)
        await session.flush()
    return aplicacion


# --- Cobros SaaS ---


async def listar_cobros(session: AsyncSession, cuenta_id: uuid.UUID) -> list[CobroSaas]:
    filas = await session.execute(
        select(CobroSaas).where(CobroSaas.cuenta_id == cuenta_id).order_by(CobroSaas.fecha.desc())
    )
    return list(filas.scalars())


async def registrar_cobro(
    session: AsyncSession,
    cuenta_id: uuid.UUID,
    *,
    concepto: str,
    importe: Decimal,
    fecha: date,
    notas: str | None,
) -> CobroSaas:
    cobro = CobroSaas(
        cuenta_id=cuenta_id,
        concepto=concepto,
        importe=importe,
        fecha=fecha,
        origen="manual",
        notas=notas,
    )
    session.add(cobro)
    await session.flush()
    return cobro


# --- Uso de IA ---
#
# Se registra por organización (auditoría de quién/qué organización
# consumió qué), pero se lista y se factura agregado por cuenta — ver
# `modulos_activos_de_cuenta`/`tokens_del_mes_de_cuenta` más abajo.


async def listar_uso_ia_de_cuenta(
    session: AsyncSession, cuenta_id: uuid.UUID, *, limit: int = 100, offset: int = 0
) -> tuple[list[UsoIA], int]:
    organizaciones = await organizaciones_de_cuenta(session, cuenta_id)
    ids_organizaciones = [o.id for o in organizaciones]
    if not ids_organizaciones:
        return [], 0
    base = select(UsoIA).where(UsoIA.organization_id.in_(ids_organizaciones))
    total = await session.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
    filas = await session.execute(
        base.order_by(UsoIA.created_at.desc()).limit(limit).offset(offset)
    )
    return list(filas.scalars()), int(total or 0)


async def registrar_uso_ia(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    usuario_subject: str,
    usuario_nombre: str,
    proveedor: str,
    modelo: str,
    tokens_entrada: int,
    tokens_salida: int,
    referencia: str | None,
) -> UsoIA:
    uso = UsoIA(
        organization_id=organization_id,
        usuario_subject=usuario_subject,
        usuario_nombre=usuario_nombre,
        proveedor=proveedor,
        modelo=modelo,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
        referencia=referencia,
    )
    session.add(uso)
    await session.flush()
    return uso


async def tokens_del_mes_de_cuenta(
    session: AsyncSession, cuenta_id: uuid.UUID
) -> tuple[int, int]:
    """(tokens_deepseek, tokens_gemini) consumidos desde el día 1 del mes en
    curso por TODAS las organizaciones de la cuenta — es la ventana que usa
    el coste estimado del mes."""
    organizaciones = await organizaciones_de_cuenta(session, cuenta_id)
    ids_organizaciones = [o.id for o in organizaciones]
    if not ids_organizaciones:
        return 0, 0

    hoy = date.today()
    inicio_mes = hoy.replace(day=1)

    filas = await session.execute(
        select(UsoIA.proveedor, func.sum(UsoIA.tokens_entrada + UsoIA.tokens_salida))
        .where(UsoIA.organization_id.in_(ids_organizaciones), UsoIA.created_at >= inicio_mes)
        .group_by(UsoIA.proveedor)
    )
    totales = {proveedor: int(suma or 0) for proveedor, suma in filas.all()}
    return totales.get("deepseek", 0), totales.get("gemini", 0)


async def modulos_activos_de_cuenta(session: AsyncSession, cuenta_id: uuid.UUID) -> list[str]:
    """Códigos de módulo activos, UNO POR CADA organización que lo tenga
    activo — no un `set` deduplicado. Cada organización es una suscripción
    propia dentro del contrato de la cuenta: si dos organizaciones de la
    misma cuenta tienen "obras" activo, se paga dos veces, no una — igual
    que cualquier plan SaaS que consolida varias licencias en una factura.
    `calcular_coste_mensual` suma duplicados porque itera la lista tal cual
    contra el precio del módulo en la tarifa.

    `organization_module` SÍ lleva RLS (a diferencia del resto de tablas de
    este módulo) — hace falta `fijar_organizacion_activa` antes de leer la
    de cada organización, o la política la oculta en cuanto no coincide con
    la organización activa de la sesión (mismo hallazgo que la Fase 11)."""
    organizaciones = await organizaciones_de_cuenta(session, cuenta_id)
    codigos: list[str] = []
    for organizacion in organizaciones:
        await fijar_organizacion_activa(session, organizacion.id)
        activos = await core_service.active_module_codes(session, organizacion.id)
        codigos.extend(activos)
    return codigos


# --- Coste estimado ---


def aplicacion_vigente(aplicacion: CuentaDescuento, hoy: date) -> bool:
    if aplicacion.anulado_en is not None:
        return False
    descuento = aplicacion.descuento
    if not descuento.activo:
        return False
    if descuento.vigente_desde and hoy < descuento.vigente_desde:
        return False
    if descuento.vigente_hasta and hoy > descuento.vigente_hasta:
        return False
    return True


def calcular_coste_mensual(
    *,
    tarifa: Tarifa | None,
    modulos_activos: Sequence[str],
    tokens_deepseek: int,
    tokens_gemini: int,
    aplicaciones: list[CuentaDescuento],
) -> dict:
    """Módulos activos × precio de la tarifa + tokens consumidos este mes ×
    precio por 1000, con los descuentos aplicados y vigentes: primero los
    porcentuales (uno tras otro sobre lo que quede), luego los de importe
    fijo, sin bajar de cero. Una aplicación anulada, o cuyo descuento se haya
    dado de baja o esté fuera de su ventana de fechas, no cuenta.

    `modulos_activos` es una secuencia que PUEDE repetir un código — una vez
    por cada organización de la cuenta que lo tenga activo (ver
    `modulos_activos_de_cuenta`), no un conjunto deduplicado: cada aparición
    cuenta como una suscripción propia.
    """
    if tarifa is None:
        cero = Decimal("0.00")
        return {
            "subtotal_modulos": cero,
            "subtotal_ia": cero,
            "subtotal": cero,
            "descuentos_aplicados": cero,
            "total": cero,
        }

    conteo_modulos = Counter(modulos_activos)
    subtotal_modulos = redondear_precio(
        sum(
            (m.precio_mensual * conteo_modulos[m.module_code] for m in tarifa.modulos),
            Decimal("0.00"),
        )
    )
    coste_ia = redondear_precio(
        Decimal(tokens_deepseek) / Decimal("1000") * tarifa.precio_1000_tokens_deepseek
        + Decimal(tokens_gemini) / Decimal("1000") * tarifa.precio_1000_tokens_gemini
    )
    subtotal = subtotal_modulos + coste_ia

    hoy = date.today()
    descuentos_vigentes = [
        a.descuento for a in aplicaciones if aplicacion_vigente(a, hoy)
    ]

    importe = subtotal
    for descuento in descuentos_vigentes:
        if descuento.tipo == TipoDescuento.PORCENTAJE:
            importe = redondear_precio(importe * (Decimal("100") - descuento.valor) / Decimal("100"))
    for descuento in descuentos_vigentes:
        if descuento.tipo == TipoDescuento.IMPORTE_FIJO:
            importe -= descuento.valor
    total = max(importe, Decimal("0.00"))

    return {
        "subtotal_modulos": subtotal_modulos,
        "subtotal_ia": coste_ia,
        "subtotal": subtotal,
        "descuentos_aplicados": redondear_precio(subtotal - total),
        "total": redondear_precio(total),
    }
