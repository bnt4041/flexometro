import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.facturacion.models import (
    Certificacion,
    CertificacionLinea,
    Cobro,
    EstadoFactura,
    Factura,
)
from app.modules.facturacion.service import importes_certificacion, situacion_cobro


def factura(total: str, estado=EstadoFactura.EMITIDA, vencimiento: date | None = None) -> Factura:
    f = Factura(
        id=uuid.uuid4(),
        codigo="FAC00001",
        serie="2026",
        numero=1,
        obra_id=uuid.uuid4(),
        cliente_id=uuid.uuid4(),
        concepto="Prueba",
        total=Decimal(total),
        base_imponible=Decimal(total),
        cuota_iva=Decimal("0.00"),
        estado=estado,
        fecha_vencimiento=vencimiento,
    )
    f.cobros = []
    return f


def cobro(importe: str) -> Cobro:
    return Cobro(id=uuid.uuid4(), importe=Decimal(importe), fecha=date.today())


# --- Situación de cobro ---


def test_sin_cobros_esta_pendiente():
    f = factura("1000.00")
    cobrado, pendiente, situacion, vencida = situacion_cobro(f)
    assert cobrado == Decimal("0.00")
    assert pendiente == Decimal("1000.00")
    assert situacion == "pendiente"
    assert not vencida


def test_cobro_parcial():
    f = factura("1000.00")
    f.cobros = [cobro("400.00")]
    cobrado, pendiente, situacion, _ = situacion_cobro(f)
    assert cobrado == Decimal("400.00")
    assert pendiente == Decimal("600.00")
    assert situacion == "parcial"


def test_cobro_completo_en_varios_pagos():
    f = factura("1000.00")
    f.cobros = [cobro("400.00"), cobro("600.00")]
    cobrado, pendiente, situacion, _ = situacion_cobro(f)
    assert cobrado == Decimal("1000.00")
    assert pendiente == Decimal("0.00")
    assert situacion == "cobrada"


def test_un_borrador_no_tiene_situacion_de_cobro():
    """Solo una factura EMITIDA tiene número fiscal y sentido de "cobrarse"."""
    f = factura("1000.00", estado=EstadoFactura.BORRADOR)
    _, _, situacion, vencida = situacion_cobro(f)
    assert situacion == "-"
    assert not vencida


def test_vencida_si_paso_la_fecha_y_no_esta_cobrada():
    f = factura("1000.00", vencimiento=date.today() - timedelta(days=5))
    _, _, _, vencida = situacion_cobro(f)
    assert vencida


def test_no_vencida_si_ya_esta_cobrada_aunque_paso_la_fecha():
    f = factura("1000.00", vencimiento=date.today() - timedelta(days=5))
    f.cobros = [cobro("1000.00")]
    _, _, situacion, vencida = situacion_cobro(f)
    assert situacion == "cobrada"
    assert not vencida


def test_no_vencida_sin_fecha_de_vencimiento():
    f = factura("1000.00", vencimiento=None)
    _, _, _, vencida = situacion_cobro(f)
    assert not vencida


def test_cobro_de_mas_no_deja_pendiente_negativo_como_cobrada():
    """Un cobro que se pasa (redondeos, cobro de más) sigue contando cobrada,
    no rompe el estado."""
    f = factura("1000.00")
    f.cobros = [cobro("1000.01")]
    _, pendiente, situacion, _ = situacion_cobro(f)
    assert pendiente == Decimal("-0.01")
    assert situacion == "cobrada"


# --- Importes de certificación ---


def linea(medicion_periodo: str, precio: str) -> CertificacionLinea:
    return CertificacionLinea(
        id=uuid.uuid4(),
        partida_id=uuid.uuid4(),
        codigo="U001",
        resumen="Prueba",
        unidad="m2",
        precio=Decimal(precio),
        medicion_anterior=Decimal("0"),
        medicion_actual=Decimal(medicion_periodo),
        medicion_periodo=Decimal(medicion_periodo),
        importe_periodo=(Decimal(medicion_periodo) * Decimal(precio)).quantize(Decimal("0.01")),
    )


def certificacion(pct_retencion: str, *lineas: CertificacionLinea) -> Certificacion:
    c = Certificacion(
        id=uuid.uuid4(),
        codigo="CERT00001",
        numero=1,
        obra_id=uuid.uuid4(),
        fecha=date.today(),
        retencion_garantia_pct=Decimal(pct_retencion),
    )
    c.lineas = list(lineas)
    return c


def test_importes_sin_retencion():
    c = certificacion("0.00", linea("74.592", "44.77"))
    importes = importes_certificacion(c)
    assert importes["importe_ejecutado"] == Decimal("3339.48")
    assert importes["importe_retenido"] == Decimal("0.00")
    assert importes["importe_liquido"] == Decimal("3339.48")


def test_importes_con_retencion_de_garantia():
    c = certificacion("5.00", linea("74.592", "44.77"))
    importes = importes_certificacion(c)
    assert importes["importe_ejecutado"] == Decimal("3339.48")
    assert importes["importe_retenido"] == Decimal("166.97")
    assert importes["importe_liquido"] == Decimal("3172.51")


def test_importes_de_varias_lineas_se_suman():
    c = certificacion("0.00", linea("10.000", "50.00"), linea("2.000", "100.00"))
    importes = importes_certificacion(c)
    assert importes["importe_ejecutado"] == Decimal("700.00")


def test_certificacion_sin_lineas_no_rompe():
    c = certificacion("5.00")
    importes = importes_certificacion(c)
    assert importes["importe_ejecutado"] == Decimal("0.00")
    assert importes["importe_liquido"] == Decimal("0.00")
