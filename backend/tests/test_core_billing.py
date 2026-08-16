import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.core.billing_models import (
    CuentaDescuento,
    Descuento,
    Tarifa,
    TarifaModulo,
    TipoDescuento,
)
from app.modules.core.billing_schemas import DescuentoCreate
from app.modules.core.billing_service import (
    DescuentoInvalido,
    calcular_coste_mensual,
    crear_descuento,
)
from app.core.secretos import generar_password_temporal


def _tarifa(precio_deepseek="0.50", precio_gemini="0.30", modulos=None) -> Tarifa:
    tarifa = Tarifa(
        id=uuid.uuid4(),
        nombre="Estándar",
        precio_1000_tokens_deepseek=Decimal(precio_deepseek),
        precio_1000_tokens_gemini=Decimal(precio_gemini),
    )
    tarifa.modulos = modulos or []
    return tarifa


def _modulo(code: str, precio: str) -> TarifaModulo:
    return TarifaModulo(module_code=code, precio_mensual=Decimal(precio))


def _aplicacion(
    tipo: TipoDescuento,
    valor: str,
    *,
    activo: bool = True,
    desde=None,
    hasta=None,
    anulado=False,
) -> CuentaDescuento:
    """Una aplicación de descuento vigente por defecto, envolviendo un
    Descuento de catálogo — es como `calcular_coste_mensual` las recibe
    ahora, en vez de una lista plana de Descuento."""
    descuento = Descuento(
        id=uuid.uuid4(),
        nombre="Test",
        tipo=tipo,
        valor=Decimal(valor),
        activo=activo,
        vigente_desde=desde,
        vigente_hasta=hasta,
    )
    aplicacion = CuentaDescuento(id=uuid.uuid4(), descuento_id=descuento.id)
    aplicacion.descuento = descuento
    if anulado:
        aplicacion.anulado_en = date.today()
    return aplicacion


# --- Coste estimado ---


def test_sin_tarifa_el_coste_es_cero():
    resultado = calcular_coste_mensual(
        tarifa=None, modulos_activos=set(), tokens_deepseek=0, tokens_gemini=0, aplicaciones=[]
    )
    assert resultado["total"] == Decimal("0.00")


def test_coste_por_modulos_activos():
    tarifa = _tarifa(
        modulos=[_modulo("presupuestos", "20.00"), _modulo("obras", "15.00"), _modulo("compras", "10.00")]
    )
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos", "obras"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=[],
    )
    assert resultado["subtotal_modulos"] == Decimal("35.00")
    assert resultado["total"] == Decimal("35.00")


def test_modulo_repetido_se_cobra_una_vez_por_aparicion():
    """Fase 14: `modulos_activos` puede traer un código repetido, una vez por
    cada organización de la cuenta que lo tenga activo — cada aparición es
    una suscripción propia, no una deduplicación."""
    tarifa = _tarifa(modulos=[_modulo("obras", "15.00")])
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos=["obras", "obras", "obras"],
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=[],
    )
    assert resultado["subtotal_modulos"] == Decimal("45.00")
    assert resultado["total"] == Decimal("45.00")


def test_coste_de_tokens_ia():
    tarifa = _tarifa(precio_deepseek="1.00", precio_gemini="2.00")
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos=set(),
        tokens_deepseek=5000,
        tokens_gemini=1000,
        aplicaciones=[],
    )
    assert resultado["subtotal_ia"] == Decimal("7.00")
    assert resultado["total"] == Decimal("7.00")


def test_descuento_porcentual_se_aplica_sobre_el_subtotal():
    tarifa = _tarifa(modulos=[_modulo("presupuestos", "100.00")])
    aplicaciones = [_aplicacion(TipoDescuento.PORCENTAJE, "10")]
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=aplicaciones,
    )
    assert resultado["total"] == Decimal("90.00")
    assert resultado["descuentos_aplicados"] == Decimal("10.00")


def test_descuento_importe_fijo():
    tarifa = _tarifa(modulos=[_modulo("presupuestos", "100.00")])
    aplicaciones = [_aplicacion(TipoDescuento.IMPORTE_FIJO, "15.00")]
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=aplicaciones,
    )
    assert resultado["total"] == Decimal("85.00")


def test_descuento_no_baja_de_cero():
    tarifa = _tarifa(modulos=[_modulo("presupuestos", "10.00")])
    aplicaciones = [_aplicacion(TipoDescuento.IMPORTE_FIJO, "50.00")]
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=aplicaciones,
    )
    assert resultado["total"] == Decimal("0.00")


def test_descuento_fuera_de_vigencia_no_se_aplica():
    tarifa = _tarifa(modulos=[_modulo("presupuestos", "100.00")])
    ayer = date.today() - timedelta(days=1)
    aplicaciones = [_aplicacion(TipoDescuento.PORCENTAJE, "50", hasta=ayer)]
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=aplicaciones,
    )
    assert resultado["total"] == Decimal("100.00")


def test_descuento_inactivo_no_se_aplica():
    tarifa = _tarifa(modulos=[_modulo("presupuestos", "100.00")])
    aplicaciones = [_aplicacion(TipoDescuento.PORCENTAJE, "50", activo=False)]
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=aplicaciones,
    )
    assert resultado["total"] == Decimal("100.00")


def test_aplicacion_anulada_no_se_aplica():
    tarifa = _tarifa(modulos=[_modulo("presupuestos", "100.00")])
    aplicaciones = [_aplicacion(TipoDescuento.PORCENTAJE, "50", anulado=True)]
    resultado = calcular_coste_mensual(
        tarifa=tarifa,
        modulos_activos={"presupuestos"},
        tokens_deepseek=0,
        tokens_gemini=0,
        aplicaciones=aplicaciones,
    )
    assert resultado["total"] == Decimal("100.00")


# --- Validación al crear un descuento de catálogo ---


async def test_descuento_porcentual_no_puede_superar_100():
    datos = DescuentoCreate(nombre="x", tipo=TipoDescuento.PORCENTAJE, valor=Decimal("150"))
    with pytest.raises(DescuentoInvalido):
        await crear_descuento(None, datos)  # type: ignore[arg-type]


# --- Contraseña temporal del alta de usuario ---


def test_password_temporal_tiene_la_longitud_pedida():
    assert len(generar_password_temporal(16)) == 16


def test_password_temporal_no_se_repite():
    generadas = {generar_password_temporal() for _ in range(20)}
    assert len(generadas) == 20
