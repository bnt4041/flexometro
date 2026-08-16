"""Contexto de organización y de usuario activos para la request en curso.

El ContextVar es la fuente de verdad dentro de la request: lo puebla el
middleware a partir del principal autenticado, y lo leen tanto la sesión de
base de datos como los servicios de cada módulo. Ningún módulo debe recibir el
organization_id ni el usuario por parámetro desde el router — se toma de aquí,
igual que ya se hacía con la organización antes de esta fase.
"""

import uuid
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.auth import Principal

_organization_id: ContextVar[uuid.UUID | None] = ContextVar("organization_id", default=None)
_principal: ContextVar["Principal | None"] = ContextVar("principal", default=None)


def current_organization_id() -> uuid.UUID | None:
    return _organization_id.get()


def require_organization_id() -> uuid.UUID:
    org_id = _organization_id.get()
    if org_id is None:
        raise RuntimeError("No hay organización activa en el contexto de la request")
    return org_id


def set_organization_id(org_id: uuid.UUID | None) -> Token:
    return _organization_id.set(org_id)


def reset_organization_id(token: Token) -> None:
    _organization_id.reset(token)


def current_principal() -> "Principal | None":
    return _principal.get()


def require_principal() -> "Principal":
    principal = _principal.get()
    if principal is None:
        raise RuntimeError("No hay usuario activo en el contexto de la request")
    return principal


def set_principal(principal: "Principal | None") -> Token:
    return _principal.set(principal)


def reset_principal(token: Token) -> None:
    _principal.reset(token)


def datos_autoria() -> dict[str, str]:
    """Para pasar por `**` al crear un registro: quién lo está creando ahora
    mismo, en el mismo formato que las columnas de `AutoriaMixin`."""
    principal = require_principal()
    return {"creado_por_subject": principal.subject, "creado_por_nombre": principal.username}
