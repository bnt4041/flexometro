"""Autenticación por clave de API.

Una integración entra con `Authorization: Bearer flx_…` o `X-API-Key`, sin
navegador y sin Keycloak. Lo que se construye es un `Principal` normal, así
que TODO lo de después —RLS, `require_permiso`, auditoría— funciona igual sin
enterarse de que no hay una persona detrás.

El `subject` de esa clave es `clave:<uuid>`, y eso es deliberado: los
registros que cree quedan firmados por la integración y no por un usuario que
no ha hecho nada. Cuando alguien pregunte «¿quién ha creado esto?», la
respuesta será el nombre de la clave.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthBackend, Principal, SinAutenticar
from app.modules.desarrolladores.models import ClaveApi

#: Prefijo visible. Sirve para reconocer de un vistazo que una cadena suelta
#: es una credencial de Flexómetro —y para que los buscadores de secretos de
#: GitHub y compañía puedan detectarla si alguien la sube por error.
MARCA = "flx_"
_LONGITUD_PREFIJO = 8

#: Cada cuánto se refresca `ultimo_uso_en`. Ver `autenticar_clave`.
RESOLUCION_USO = timedelta(minutes=1)


def generar_clave() -> tuple[str, str, str]:
    """Devuelve `(clave_en_claro, prefijo, hash)`.

    El claro se enseña UNA vez al crearla y no se guarda: es lo que hace que
    filtrar la tabla no sirva de nada.
    """
    secreto = secrets.token_urlsafe(32)
    clave = f"{MARCA}{secreto}"
    return clave, secreto[:_LONGITUD_PREFIJO], hashlib.sha256(clave.encode()).hexdigest()


def _clave_de(request: Request) -> str | None:
    """La clave que viene en la petición, si la hay."""
    directa = request.headers.get("x-api-key")
    if directa and directa.startswith(MARCA):
        return directa
    cabecera = request.headers.get("authorization") or ""
    if cabecera.lower().startswith("bearer "):
        valor = cabecera[7:].strip()
        # Solo si lleva nuestra marca: un JWT de Keycloak viaja por la misma
        # cabecera y no debe acabar aquí.
        if valor.startswith(MARCA):
            return valor
    return None


async def autenticar_clave(session: AsyncSession, clave: str) -> Principal:
    """El principal de esa clave. Lanza `SinAutenticar` si no vale.

    Los motivos van todos con el mismo mensaje a propósito: distinguir «no
    existe» de «caducada» le diría a quien prueba claves cuáles ha acertado.
    """
    secreto = clave[len(MARCA) :]
    fila = await session.scalar(
        select(ClaveApi).where(ClaveApi.prefijo == secreto[:_LONGITUD_PREFIJO])
    )
    esperado = hashlib.sha256(clave.encode()).hexdigest()
    # `compare_digest` incluso teniendo ya la fila: comparar hashes con `==`
    # filtra información por el tiempo que tarda en fallar.
    if fila is None or not secrets.compare_digest(fila.clave_hash, esperado):
        raise SinAutenticar("Clave de API no válida")
    if not fila.activa:
        raise SinAutenticar("Clave de API no válida")
    if fila.expira_en is not None and fila.expira_en <= datetime.now(UTC):
        raise SinAutenticar("Clave de API no válida")

    # Marca de uso, para poder retirar las que ya nadie usa.
    #
    # No se escribe en cada petición: una integración activa haría un UPDATE
    # por llamada, y el dato que interesa es «cuándo fue la última vez», con
    # un minuto de resolución de sobra. Sin esta guarda, una API con tráfico
    # convierte cada lectura en una escritura.
    ahora = datetime.now(UTC)
    if fila.ultimo_uso_en is None or (ahora - fila.ultimo_uso_en) > RESOLUCION_USO:
        # UPDATE de Core y no `fila.ultimo_uso_en = ahora`, por dos motivos
        # que se juntan aquí:
        #
        # 1. El audit trail escucha `before_flush` del ORM. Tocando el objeto,
        #    CADA llamada a la API dejaría una fila de auditoría diciendo
        #    «clave modificada» — y ahogaría el registro que sí importa.
        # 2. Esa fila de auditoría se insertaría sin organización en contexto:
        #    esto corre ANTES de que el middleware la fije, así que RLS la
        #    rechaza y la petición entera revienta con un 500.
        await session.execute(
            update(ClaveApi).where(ClaveApi.id == fila.id).values(ultimo_uso_en=ahora)
        )
        # Commit propio: esta sesión es solo del middleware de autenticación
        # (ver `TenancyMiddleware`), aparte de la que use luego el endpoint.
        await session.commit()

    return Principal(
        subject=f"clave:{fila.id}",
        organization_id=fila.organization_id,
        organization_slug=None,
        username=fila.nombre,
        # Sin roles: una clave nunca es `admin`. Lo que puede hacer sale de
        # sus ámbitos, y así no hay forma de que una integración se salte los
        # permisos por la puerta de atrás del rol.
        roles=frozenset(),
    )


class ConClavesApi:
    """Envuelve el backend de autenticación de siempre.

    Se hace por envoltura y no tocando `KeycloakAuthBackend` para que las dos
    formas de entrar sigan siendo independientes: si esto falla, el login de
    personas no se entera.
    """

    def __init__(self, siguiente: AuthBackend) -> None:
        self._siguiente = siguiente

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal:
        clave = _clave_de(request)
        if clave is not None:
            return await autenticar_clave(session, clave)
        return await self._siguiente.authenticate(request, session)
