"""Validación de tokens contra el realm de Keycloak.

Se valida la firma con las claves públicas del realm (JWKS), que se descargan
una vez y se guardan en memoria. Si llega un token firmado con una clave que no
está en la caché —rotación de claves—, se vuelven a pedir una sola vez antes de
rechazarlo.

Nunca se consulta a Keycloak para validar un token concreto: eso metería una
llamada de red en cada request. Con la firma y las fechas basta.
"""

import logging
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKSet

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Las claves de un realm cambian muy de tarde en tarde; una hora es holgado y
# la rotación se detecta igualmente por el `kid` desconocido.
TTL_CLAVES = 3600


class TokenInvalido(Exception):
    pass


class ValidadorTokens:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._claves: dict[str, Any] = {}
        self._descargadas_en: float = 0.0

    async def _descargar_claves(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as cliente:
                respuesta = await cliente.get(self._settings.jwks_url)
                respuesta.raise_for_status()
                conjunto = PyJWKSet.from_dict(respuesta.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise TokenInvalido(
                f"No se han podido obtener las claves del realm: {exc}"
            ) from exc

        self._claves = {clave.key_id: clave.key for clave in conjunto.keys if clave.key_id}
        self._descargadas_en = time.monotonic()
        logger.info("Claves del realm actualizadas: %d", len(self._claves))

    async def _clave_para(self, kid: str):
        caducadas = time.monotonic() - self._descargadas_en > TTL_CLAVES
        if not self._claves or caducadas:
            await self._descargar_claves()
        if kid not in self._claves:
            # Puede ser rotación: se reintenta una vez antes de rendirse.
            await self._descargar_claves()
        if kid not in self._claves:
            raise TokenInvalido("El token está firmado con una clave desconocida")
        return self._claves[kid]

    async def validar(self, token: str) -> dict[str, Any]:
        try:
            cabecera = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenInvalido("El token no tiene un formato válido") from exc

        kid = cabecera.get("kid")
        if not kid:
            raise TokenInvalido("El token no indica con qué clave se firmó")

        clave = await self._clave_para(kid)

        try:
            datos = jwt.decode(
                token,
                key=clave,
                algorithms=["RS256", "RS512", "ES256"],
                audience=self._settings.keycloak_client_id,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenInvalido("El token ha caducado") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenInvalido(
                f"El token no va dirigido a '{self._settings.keycloak_client_id}'"
            ) from exc
        except jwt.PyJWTError as exc:
            raise TokenInvalido(f"Token rechazado: {exc}") from exc

        # El emisor se comprueba a mano porque hay dos válidos: la URL interna
        # y la pública, y PyJWT solo admite una.
        emisor = datos.get("iss", "")
        if emisor not in self._settings.emisores_validos:
            raise TokenInvalido(f"Emisor no reconocido: '{emisor}'")

        return datos
