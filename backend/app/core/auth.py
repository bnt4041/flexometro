"""Autenticación.

La interfaz es la definitiva; el backend `stub` es lo provisional. En Fase 5 se
implementa `KeycloakAuthBackend` validando el JWT contra el realm y poblando el
mismo `Principal` — ningún módulo de negocio necesita cambiar, porque todos
dependen de `get_principal`, no del mecanismo.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.keycloak import TokenInvalido, ValidadorTokens


@dataclass(frozen=True)
class Principal:
    """Quién hace la request y en nombre de qué organización.

    `organization_id`/`organization_slug` son `None` para el personal de la
    plataforma (rol `superadmin` sin ninguna organización propia, ver Fase
    13) — solo puede entrar a `/api/admin/*`, que no depende de una
    organización activa salvo cuando administra una en concreto (vía
    `fijar_organizacion_activa()`). Cualquier otro principal SIEMPRE tiene
    organización: `KeycloakAuthBackend` no deja pasar a nadie sin ella salvo
    que tenga ese rol."""

    subject: str
    organization_id: uuid.UUID | None
    organization_slug: str | None
    username: str
    roles: frozenset[str] = field(default_factory=frozenset)
    # Todas las organizaciones a las que el usuario puede entrar. La activa es
    # `organization_slug`; entre estas puede conmutar sin volver a iniciar
    # sesión. Vacía para el personal de la plataforma.
    organizaciones: tuple[str, ...] = ()

    def has_role(self, role: str) -> bool:
        return role in self.roles


class AuthBackend(Protocol):
    async def authenticate(self, request: Request, session: AsyncSession) -> Principal: ...


class StubAuthBackend:
    """Principal fijo de desarrollo, resuelto contra la organización semilla.

    No valida nada: existe para que el resto del sistema pueda asumir que
    siempre hay un Principal y una organización activa.
    """

    def __init__(self, organization_slug: str) -> None:
        self._organization_slug = organization_slug

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal:
        # Import diferido: el módulo core importa el auth, no al revés.
        from app.modules.core.models import Organization

        slug = request.headers.get("X-Organization-Slug", self._organization_slug)
        org = (
            await session.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()

        if org is None:
            raise LookupError(
                f"La organización '{slug}' no existe. "
                "¿Se ha ejecutado la migración semilla del módulo core?"
            )

        return Principal(
            subject="stub-user",
            organization_id=org.id,
            organization_slug=org.slug,
            username="dev",
            roles=frozenset({"admin"}),
            organizaciones=(org.slug,),
        )


class SinAutenticar(Exception):
    """No hay credenciales, o no valen. Se traduce a 401."""


class SinOrganizacion(Exception):
    """El usuario está autenticado pero no puede entrar aquí. Se traduce a 403."""


ROL_SUPERADMIN = "superadmin"


class KeycloakAuthBackend:
    """Principal a partir del JWT del realm.

    Implementa la misma interfaz que el stub, así que ningún módulo de negocio
    cambia: todos dependen de `get_principal`, no del mecanismo.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._validador = ValidadorTokens(settings)

    async def authenticate(self, request: Request, session: AsyncSession) -> Principal:
        from app.modules.core.models import Organization

        cabecera = request.headers.get("Authorization", "")
        if not cabecera.lower().startswith("bearer "):
            raise SinAutenticar("Falta la cabecera Authorization con un token Bearer")

        try:
            datos = await self._validador.validar(cabecera[7:].strip())
        except TokenInvalido as exc:
            raise SinAutenticar(str(exc)) from exc

        roles = frozenset(datos.get("realm_access", {}).get("roles", []))
        username = datos.get("preferred_username") or datos.get("email") or datos["sub"]

        slugs = self._organizaciones_de(datos)
        if not slugs:
            # Personal de la plataforma (Fase 13): sin el atributo
            # `organizacion` en absoluto. Solo se admite sin organización si
            # tiene el rol que lo justifica — cualquier otro usuario sin el
            # atributo sigue siendo un error de aprovisionamiento, no un
            # personal de plataforma silencioso.
            if ROL_SUPERADMIN in roles:
                return Principal(
                    subject=datos["sub"],
                    organization_id=None,
                    organization_slug=None,
                    username=username,
                    roles=roles,
                    organizaciones=(),
                )
            raise SinOrganizacion(
                f"El usuario no tiene el atributo '{self._settings.keycloak_claim_organizacion}' "
                "en Keycloak, así que no se sabe en qué organización entra"
            )

        # Con varias organizaciones, la cabecera elige entre las suyas; sin
        # ella, la primera. Nunca se acepta una que no esté en el token.
        pedida = request.headers.get("X-Organization-Slug")
        if pedida and pedida not in slugs:
            raise SinOrganizacion(
                f"El usuario no pertenece a la organización '{pedida}'"
            )
        slug = pedida or slugs[0]

        org = (
            await session.execute(select(Organization).where(Organization.slug == slug))
        ).scalar_one_or_none()
        if org is None:
            raise SinOrganizacion(
                f"La organización '{slug}' existe en Keycloak pero no en la aplicación"
            )
        if not org.is_active:
            raise SinOrganizacion(f"La organización '{slug}' está desactivada")

        return Principal(
            subject=datos["sub"],
            organization_id=org.id,
            organization_slug=org.slug,
            username=username,
            roles=roles,
            organizaciones=tuple(slugs),
        )

    def _organizaciones_de(self, datos: dict) -> list[str]:
        """El claim puede venir como texto o como lista, según el mapeador."""
        crudo = datos.get(self._settings.keycloak_claim_organizacion)
        if not crudo:
            return []
        if isinstance(crudo, str):
            return [t.strip() for t in crudo.split(",") if t.strip()]
        return [str(t).strip() for t in crudo if str(t).strip()]


def build_auth_backend(settings: Settings) -> AuthBackend:
    base: AuthBackend
    if settings.auth_backend == "keycloak":
        base = KeycloakAuthBackend(settings)
    else:
        base = StubAuthBackend(settings.stub_organization_slug)

    # Las claves de API van por delante, pero solo se quedan la petición si
    # traen la marca `flx_`: un JWT de Keycloak viaja por la misma cabecera
    # `Authorization` y tiene que seguir su camino de siempre.
    from app.modules.desarrolladores.claves import ConClavesApi

    return ConClavesApi(base)


def get_auth_backend(settings: Settings = Depends(get_settings)) -> AuthBackend:
    return build_auth_backend(settings)


async def get_principal(request: Request) -> Principal:
    """El middleware de tenancy ya ha autenticado y guardado el principal."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise RuntimeError("No hay principal en la request; ¿falta el TenancyMiddleware?")
    return principal


async def require_superadmin(principal: Principal = Depends(get_principal)) -> Principal:
    """Guarda de router para la administración de organizaciones.

    Es un rol de Keycloak más, no un mecanismo de login aparte: quien lo tiene
    entra por la misma pantalla que cualquier usuario de un tenant. Desde la
    Fase 13 ya NO pertenece a ninguna organización (`organization_id` es
    `None` para este principal) — el rol solo desbloquea la sección de
    administración del shell.
    """
    if not principal.has_role(ROL_SUPERADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requiere el rol '{ROL_SUPERADMIN}'",
        )
    return principal


ROL_ADMIN_ORGANIZACION = "admin"


async def require_admin_organizacion(principal: Principal = Depends(get_principal)) -> Principal:
    """Guarda de router para el autoservicio de usuarios y grupos de la
    Fase 12: el rol `admin` (administra su organización, existe desde la
    Fase 6) puede gestionar los usuarios y grupos de SU PROPIA organización,
    sin depender del superadmin. A diferencia de `require_superadmin`, no
    cruza la frontera de organización — opera siempre sobre la del propio
    principal, RLS de por medio como cualquier request normal.

    Exige `organization_id` además del rol: desde la Fase 13, el personal de
    la plataforma puede arrastrar el rol `admin` de cuando pertenecía a una
    organización sin que nadie lo haya limpiado — sin esta comprobación,
    intentaría administrar "su" organización sin tener ninguna."""
    if not principal.has_role(ROL_ADMIN_ORGANIZACION) or principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requiere el rol '{ROL_ADMIN_ORGANIZACION}' sobre una organización",
        )
    return principal
