"""Tokens de los enlaces que se mandan a alguien de fuera (sin cuenta).

Lo mismo que ya hacía `compras/publico_acceso.py` para la separata del
proveedor, extraído aquí porque el módulo `prl` necesita exactamente el mismo
mecanismo para los enlaces de firma y duplicar código de seguridad es la peor
forma de compartirlo. `compras` conserva de momento su copia — ver el aviso de
más abajo.

Las dos reglas que hacen esto seguro, y que cualquier uso nuevo debe respetar:

1. **Nunca se guarda el token en claro**, solo su SHA-256. Si se filtrara la
   tabla, los enlaces no serían utilizables.
2. **32 bytes de entropía.** Es lo que hace aceptable un SHA-256 sin sal: con
   este tamaño no hay diccionario ni fuerza bruta viable. Un código corto y
   legible se rompería en segundos con la tabla en la mano.
"""

import hashlib
import secrets

BYTES_TOKEN = 32


def generar_token() -> tuple[str, str]:
    """Devuelve `(token_en_claro, hash)`. El claro solo viaja en el correo y
    no se guarda en ningún sitio."""
    token = secrets.token_urlsafe(BYTES_TOKEN)
    return token, hashear_token(token)


def hashear_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
