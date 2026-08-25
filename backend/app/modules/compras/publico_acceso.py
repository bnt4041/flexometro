"""Autorización del proveedor externo que abre la separata desde un enlace.

Es el único punto del sistema donde alguien opera sin haber pasado por
Keycloak, así que concentra aquí toda la delicadeza y ningún endpoint la
repite.

El problema de fondo: el proveedor llega sin sesión, luego no hay organización
en el contexto y, sin ella, RLS devuelve cero filas en toda tabla de negocio.
Hay que averiguar a qué organización pertenece su enlace ANTES de que exista
contexto — el mismo problema que resuelve `core.organization` al iniciar
sesión, y por eso la misma solución: una tabla mínima y opaca fuera de RLS
(`compras.acceso_token`) que solo sabe traducir un hash en una organización.
A partir de ahí se fija el contexto y **el RLS vuelve a ser el cortafuegos**,
igual que en cualquier otra petición.

Reglas que este módulo garantiza, cada una por un fallo concreto:

- **Las tres fuentes de identidad se fijan a la vez** y todas desde el token:
  la variable de PostgreSQL (lo que ve RLS), el ContextVar de `tenancy` (lo
  que leen los servicios y `datos_autoria`) y `request.state.principal` (lo
  que lee `get_principal`). Dejar una sin fijar es la trampa documentada en
  `presupuestos/versionado.py:409-413`, donde las dos primeras divergen.
- **`flush` antes de soltar el principal.** FastAPI cierra las dependencias
  en orden inverso, así que el `reset` de aquí ocurre *antes* del `commit` de
  `get_session`: sin este flush explícito, el listener de auditoría leería un
  principal ya vacío y grabaría el cambio sin autor.
- **El principal sintético no lleva ningún rol.** Aunque se colara en un
  endpoint normal, `require_permiso` acaba en alcance NINGUNO y las guardas
  de admin exigen rol: no abre nada.
- **Un único 404 para todo**: token desconocido, caducado, revocado o de una
  solicitud que ya no admite respuesta. Sin distinguir, y sin decir de qué
  organización ni de quién era.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.database import fijar_organizacion_activa, get_session
from app.core.tenancy import (
    reset_organization_id,
    reset_principal,
    set_organization_id,
    set_principal,
)
from app.modules.compras.models import (
    AccesoEstado,
    AccesoToken,
    EstadoSolicitud,
    SolicitudPrecios,
)

# 32 bytes de entropía. Es lo que hace aceptable guardar un SHA-256 sin sal:
# con este tamaño no hay diccionario ni fuerza bruta viable, mientras que un
# código corto y legible se rompería en segundos si se filtrara la tabla.
BYTES_TOKEN = 32

# Estados en los que el enlace sigue admitiendo respuesta del proveedor.
_ESTADOS_ABIERTOS = frozenset({EstadoSolicitud.ENVIADA, EstadoSolicitud.RESPONDIDA})


def generar_token() -> tuple[str, str]:
    """Devuelve `(token_en_claro, hash)`. El claro solo viaja en el correo y
    no se guarda en ningún sitio."""
    token = secrets.token_urlsafe(BYTES_TOKEN)
    return token, hashear_token(token)


def hashear_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class ContextoProveedor:
    """Lo que un endpoint público necesita saber, ya validado."""

    solicitud: SolicitudPrecios
    estado: AccesoEstado
    organization_id: uuid.UUID


def _no_encontrado() -> HTTPException:
    """Siempre el mismo error, diga lo que diga el motivo real: distinguir
    "caducado" de "no existe" ya le confirma a quien prueba que ese enlace
    existió alguna vez."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Este enlace no es válido o ha caducado.",
    )


async def _resolver_token(session: AsyncSession, token: str) -> AccesoToken | None:
    """Traduce el token en organización. Es lo ÚNICO que se hace sin contexto,
    y por eso `acceso_token` está fuera de RLS."""
    if not token or len(token) > 200:
        return None
    return await session.scalar(
        select(AccesoToken).where(AccesoToken.token_hash == hashear_token(token))
    )


async def acceso_proveedor(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Dependencia de todo endpoint bajo `/api/publico/oferta/{token}`."""
    acceso = await _resolver_token(session, token)
    if acceso is None:
        raise _no_encontrado()

    # Nadie debería haber fijado identidad antes: el middleware se salta este
    # espacio. Si hay algo, es que la ruta dejó de ser pública sin querer.
    if getattr(request.state, "principal", None) is not None:
        raise RuntimeError(
            "La ruta pública de proveedor recibió un principal ya autenticado; "
            "revisa PUBLIC_PREFIXES en app/core/middleware.py"
        )

    org_id = acceso.organization_id

    # A partir de aquí, contexto completo y coherente: RLS vuelve a proteger.
    await fijar_organizacion_activa(session, org_id)
    token_org = set_organization_id(org_id)

    slug = await session.scalar(
        text("SELECT slug FROM core.organization WHERE id = :org_id"), {"org_id": str(org_id)}
    )
    principal = Principal(
        subject=f"proveedor:{acceso.solicitud_id}",
        organization_id=org_id,
        organization_slug=slug,
        username="Proveedor (enlace externo)",
        roles=frozenset(),  # sin roles: no supera ninguna guarda de la aplicación
    )
    token_principal = set_principal(principal)
    request.state.principal = principal

    try:
        # Ya con RLS puesto: el estado del enlace y la solicitud se leen como
        # cualquier otra tabla de negocio.
        estado = await session.scalar(
            select(AccesoEstado).where(AccesoEstado.solicitud_id == acceso.solicitud_id)
        )
        solicitud = await session.scalar(
            select(SolicitudPrecios).where(SolicitudPrecios.id == acceso.solicitud_id)
        )
        if estado is None or solicitud is None:
            raise _no_encontrado()
        if estado.revocado or estado.expira_en <= datetime.now(UTC):
            raise _no_encontrado()
        if solicitud.estado not in _ESTADOS_ABIERTOS:
            raise _no_encontrado()

        estado.usos += 1
        estado.ultimo_uso_en = datetime.now(UTC)

        yield ContextoProveedor(solicitud=solicitud, estado=estado, organization_id=org_id)

        # Con el principal todavía en contexto, para que la auditoría tenga
        # autor. El commit lo hace `get_session`, nunca el router: la variable
        # de PostgreSQL es local a la transacción y un commit a media petición
        # la vaciaría, dejando ciego todo lo que viniera después.
        await session.flush()
    finally:
        request.state.principal = None
        reset_principal(token_principal)
        reset_organization_id(token_org)
