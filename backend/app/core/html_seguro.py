"""Saneado del HTML que llega de un editor WYSIWYG (descripciones de
capítulo/partida) antes de guardarlo.

El navegador ya evita que el propio editor genere nada peligroso, pero el
campo se guarda tal cual llega por la API — y esa misma API la puede llamar
cualquiera con curl. Sanear en el servidor es lo único que de verdad protege
a quien lea esa descripción más tarde.
"""

import nh3

_ETIQUETAS_PERMITIDAS = {
    "p", "br", "strong", "em", "s", "a", "img",
    "h1", "h2", "h3", "ul", "ol", "li", "blockquote", "code", "pre",
}
_ATRIBUTOS_PERMITIDOS = {
    "a": {"href", "target"},
    "img": {"src", "alt", "data-documento-id"},
}


def sanear_html(html: str | None) -> str | None:
    if html is None:
        return None
    return nh3.clean(
        html,
        tags=_ETIQUETAS_PERMITIDAS,
        attributes=_ATRIBUTOS_PERMITIDOS,
        link_rel="noopener noreferrer",
    )
