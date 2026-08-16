import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.auth import Principal, require_superadmin
from app.modules.core.admin_schemas import OrganizacionCreate


def _principal(roles: frozenset[str]) -> Principal:
    return Principal(
        subject="u1",
        organization_id=uuid.uuid4(),
        organization_slug="demo",
        username="dev",
        roles=roles,
        organizaciones=("demo",),
    )


# --- Guarda de rol: mismo login que un usuario de tenant, un rol de más ---


async def test_require_superadmin_rechaza_sin_el_rol():
    with pytest.raises(HTTPException) as exc:
        await require_superadmin(_principal(frozenset({"admin", "usuario"})))
    assert exc.value.status_code == 403


async def test_require_superadmin_acepta_con_el_rol():
    principal = _principal(frozenset({"admin", "usuario", "superadmin"}))
    resultado = await require_superadmin(principal)
    assert resultado is principal


# --- Validación del slug de una organización nueva ---


def test_slug_valido():
    datos = OrganizacionCreate(slug="obra-verde", name="Obra Verde SL")
    assert datos.slug == "obra-verde"


@pytest.mark.parametrize(
    "slug",
    ["Mayusculas", "con_guion_bajo", "-empieza-con-guion", "acaba-con-guion-", "a"],
)
def test_slug_invalido(slug: str):
    with pytest.raises(ValidationError):
        OrganizacionCreate(slug=slug, name="X")
