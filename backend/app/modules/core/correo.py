"""Correo de bienvenida al administrador de una organización nueva."""

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
