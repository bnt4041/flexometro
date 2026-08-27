"""Plantillas de correo: bienvenida al administrador de una organización
nueva, y solicitud de precios a un proveedor."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "plantillas"),
    autoescape=select_autoescape(["html"]),
)


def render_bienvenida(
    *,
    nombre: str,
    organizacion_nombre: str | None = None,
    username: str,
    password_temporal: str,
    url_app: str,
    es_plataforma: bool = False,
) -> str:
    """`es_plataforma=True` es el alta de personal de la plataforma (Fase
    13): no hay organización que nombrar, así que `organizacion_nombre` se
    ignora."""
    plantilla = _env.get_template("bienvenida.html")
    return plantilla.render(
        nombre=nombre,
        organizacion_nombre=organizacion_nombre,
        username=username,
        password_temporal=password_temporal,
        url_app=url_app,
        es_plataforma=es_plataforma,
    )


def render_solicitud_precios(
    *,
    emisor_nombre: str,
    proveedor_nombre: str | None,
    presupuesto_nombre: str,
    titulo: str,
    emplazamiento: str | None,
    num_lineas: int,
    notas: str | None,
    fecha_limite: str | None,
    url_oferta: str | None,
    url_aplicacion: str | None = None,
    url_landing: str | None = None,
) -> str:
    plantilla = _env.get_template("solicitud_precios.html")
    return plantilla.render(
        emisor_nombre=emisor_nombre,
        proveedor_nombre=proveedor_nombre,
        presupuesto_nombre=presupuesto_nombre,
        titulo=titulo,
        emplazamiento=emplazamiento,
        num_lineas=num_lineas,
        notas=notas,
        fecha_limite=fecha_limite,
        url_oferta=url_oferta,
        url_aplicacion=url_aplicacion,
        url_landing=url_landing,
    )
