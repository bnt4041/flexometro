"""Lo que hay que blindar del copiloto: que no enseñe lo que no toca y que no
escriba por su cuenta.

No se prueba aquí que el modelo conteste bien —eso no es determinista y no es
lo que puede hacer daño—. Se prueba el filtro de permisos, que es lo que
decide qué herramientas existen siquiera para él, y el troceado de la wiki,
que es puro texto.
"""

import uuid

import pytest

from app.core.auth import Principal
from app.core.enums import Alcance
from app.core.permisos import PermisoModulo
from app.modules.ia.copiloto import herramientas as catalogo
from app.modules.ia.copiloto.registro import Contexto, disponibles

NADA = PermisoModulo(
    ver=Alcance.NINGUNO,
    editar=Alcance.NINGUNO,
    crear=Alcance.NINGUNO,
    borrar=Alcance.NINGUNO,
)
SOLO_VER = PermisoModulo(
    ver=Alcance.TODOS,
    editar=Alcance.NINGUNO,
    crear=Alcance.NINGUNO,
    borrar=Alcance.NINGUNO,
)
TODO = PermisoModulo(
    ver=Alcance.TODOS,
    editar=Alcance.TODOS,
    crear=Alcance.TODOS,
    borrar=Alcance.TODOS,
)

TODOS_LOS_MODULOS = frozenset(
    {"obras", "terceros", "presupuestos", "facturacion", "compras", "soporte", "ia"}
)


def _contexto(permisos: dict[str, PermisoModulo], modulos=TODOS_LOS_MODULOS) -> Contexto:
    catalogo.registrar_catalogo_inicial()
    principal = Principal(
        subject="alguien",
        username="alguien",
        roles=[],
        organization_id=uuid.uuid4(),
        organization_slug="prueba",
        organizaciones=["prueba"],
    )
    return Contexto(
        session=None,  # type: ignore[arg-type]
        principal=principal,
        permisos=permisos,
        modulos_activos=modulos,
    )


def test_sin_permisos_no_hay_herramientas_de_datos():
    """Quien no ve nada no recibe la herramienta de buscar. La puerta no está
    cerrada: no existe, así que el modelo ni puede intentar abrirla."""
    nombres = [h.nombre for h in disponibles(_contexto({}))]
    assert "buscar_objetos" not in nombres
    assert "ver_objeto" not in nombres
    assert "resumir_datos" not in nombres


def test_la_ayuda_no_depende_de_los_permisos():
    """Quien menos permisos tiene es justo quien más necesita poder preguntar
    y abrir un ticket."""
    nombres = [h.nombre for h in disponibles(_contexto({}))]
    assert "buscar_en_la_ayuda" in nombres
    assert "guia_de_la_interfaz" in nombres
    assert "proponer_abrir_ticket" in nombres


def test_ver_no_da_crear():
    permisos = dict.fromkeys(TODOS_LOS_MODULOS, SOLO_VER)
    nombres = [h.nombre for h in disponibles(_contexto(permisos))]
    assert "buscar_objetos" in nombres
    assert "proponer_crear" not in nombres


def test_con_permiso_de_crear_aparece_la_propuesta():
    permisos = dict.fromkeys(TODOS_LOS_MODULOS, TODO)
    nombres = [h.nombre for h in disponibles(_contexto(permisos))]
    assert "proponer_crear" in nombres


def test_se_pueden_retirar_las_de_escritura():
    """Una vez hay una propuesta en el turno no se ofrecen más: confirmar tres
    cosas de golpe con un botón es no confirmar nada."""
    permisos = dict.fromkeys(TODOS_LOS_MODULOS, TODO)
    ctx = _contexto(permisos)
    con = {h.nombre for h in disponibles(ctx)}
    sin = {h.nombre for h in disponibles(ctx, permitir_escritura=False)}
    assert con - sin == {"proponer_crear", "proponer_abrir_ticket"}


def test_un_modulo_apagado_no_asoma_aunque_haya_permiso():
    """El permiso no vale de nada si la organización no tiene ese módulo."""
    permisos = dict.fromkeys(TODOS_LOS_MODULOS, TODO)
    ctx = _contexto(permisos, modulos=frozenset({"ia"}))
    nombres = [h.nombre for h in disponibles(ctx)]
    assert "buscar_objetos" not in nombres
    assert "proponer_crear" not in nombres


def test_el_esquema_solo_enumera_lo_que_se_puede_ver():
    """El JSON Schema que ve el modelo se construye con los permisos: si
    enumerase «factura» a quien no ve facturas, el modelo la pediría y se
    llevaría un error en cada intento."""
    permisos = {"obras": SOLO_VER, "facturacion": NADA}
    ctx = _contexto(permisos, modulos=frozenset({"obras", "facturacion", "ia"}))
    buscar = next(h for h in disponibles(ctx) if h.nombre == "buscar_objetos")
    tipos = buscar.parametros(ctx)["properties"]["tipo"]["enum"]
    assert "obra" in tipos
    assert "factura" not in tipos


# ── Troceado de la wiki ─────────────────────────────────────────────────


def test_trocear_texto_corto_es_un_solo_trozo():
    from app.modules.soporte.embeddings import trocear

    assert trocear("Dos palabras") == ["Dos palabras"]
    assert trocear("") == []
    assert trocear("   \n  ") == []


def test_trocear_solapa_para_no_partir_ideas():
    from app.modules.soporte.embeddings import SOLAPE, TAMANO_TROZO, trocear

    texto = " ".join(f"palabra{i}" for i in range(600))
    trozos = trocear(texto)
    assert len(trozos) > 1
    assert all(len(t) <= TAMANO_TROZO for t in trozos)
    # El final de un trozo reaparece al principio del siguiente: sin eso, una
    # frase cortada por la mitad no la encuentra nadie.
    cola = trozos[0][-SOLAPE // 2 :].strip()
    assert cola in trozos[1]


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("Cómo dar de alta un proveedor", "como-dar-de-alta-un-proveedor"),
        ("  Espacios   de más  ", "espacios-de-mas"),
        ("¿Y esto? ¡Sí!", "y-esto-si"),
    ],
)
def test_slug_de_la_wiki(titulo, esperado):
    from app.modules.soporte.service import slugificar

    assert slugificar(titulo) == esperado
