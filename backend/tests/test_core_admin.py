import re
import uuid

import pytest
from fastapi import HTTPException

from app.core.auth import Principal, require_superadmin
from app.core.texto import slugify


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


# --- Slug de una organización nueva ---
#
# Ya no se teclea: se genera del nombre (`slug_organizacion_unico`). Así que
# no hay nada que validar y sí que garantizar — el slug viaja a Keycloak como
# atributo `organizacion`, y su alfabeto es minúsculas, dígitos y guiones.


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Obra Verde SL", "obra-verde-sl"),
        ("Construcciones Muñoz, S.A.", "construcciones-munoz-s-a"),
        ("  Espacios   de más  ", "espacios-de-mas"),
        ("Guion_bajo y MAYÚSCULAS", "guion-bajo-y-mayusculas"),
    ],
)
def test_el_slug_sale_del_nombre(nombre: str, esperado: str):
    assert slugify(nombre) == esperado


@pytest.mark.parametrize(
    "nombre",
    ["Obra Verde SL", "¡!¿?", "---", "A", "Ñ", "x" * 200, "-empieza y acaba-"],
)
def test_el_slug_generado_siempre_vale_para_keycloak(nombre: str):
    """Da igual lo que teclee quien da de alta: lo que sale tiene que entrar
    en el realm. Un slug inválido reventaría en el alta, no aquí."""
    slug = slugify(nombre)
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug), slug
    assert 2 <= len(slug) <= 64


def test_un_nombre_sin_letras_no_deja_el_slug_vacio():
    assert slugify("¡!¿?") == "empresa"
