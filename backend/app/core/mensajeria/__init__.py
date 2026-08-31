"""Mensajería saliente: un puerto y sus adaptadores.

El dominio importa de aquí; nadie fuera de `fabrica` debería importar un
adaptador concreto.
"""

from app.core.mensajeria.fabrica import (
    canales_disponibles,
    proveedor_de,
    proveedor_whatsapp,
)
from app.core.mensajeria.puerto import (
    Adjunto,
    Canal,
    CodigoQr,
    Destinatario,
    Mensaje,
    MensajeriaError,
    PreferenciaCanal,
    ProveedorMensajeria,
    TipoMensaje,
    Vinculacion,
    VinculacionPorQr,
    normalizar_telefono,
    ofuscar_email,
    ofuscar_telefono,
)

__all__ = [
    "Adjunto",
    "Canal",
    "CodigoQr",
    "Destinatario",
    "Mensaje",
    "MensajeriaError",
    "PreferenciaCanal",
    "ProveedorMensajeria",
    "TipoMensaje",
    "Vinculacion",
    "VinculacionPorQr",
    "canales_disponibles",
    "normalizar_telefono",
    "ofuscar_email",
    "ofuscar_telefono",
    "proveedor_de",
    "proveedor_whatsapp",
]
