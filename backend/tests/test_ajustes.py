import uuid

import pytest
from fastapi import HTTPException

from app.core.auth import Principal, require_admin_organizacion


def _principal(roles: frozenset[str], organization_id: uuid.UUID | None) -> Principal:
    return Principal(
        subject="u1",
        organization_id=organization_id,
        organization_slug="demo" if organization_id else None,
        username="dev",
        roles=roles,
        organizaciones=("demo",) if organization_id else (),
    )


async def test_require_admin_organizacion_rechaza_sin_el_rol():
    with pytest.raises(HTTPException) as exc:
        await require_admin_organizacion(_principal(frozenset({"usuario"}), uuid.uuid4()))
    assert exc.value.status_code == 403


async def test_require_admin_organizacion_rechaza_admin_sin_organizacion():
    """Personal de plataforma que arrastra el rol 'admin' de cuando pertenecía
    a una organización (ver Fase 13) no puede colarse en el autoservicio."""
    with pytest.raises(HTTPException) as exc:
        await require_admin_organizacion(_principal(frozenset({"admin"}), None))
    assert exc.value.status_code == 403


async def test_require_admin_organizacion_acepta_con_rol_y_organizacion():
    principal = _principal(frozenset({"admin", "usuario"}), uuid.uuid4())
    resultado = await require_admin_organizacion(principal)
    assert resultado is principal
