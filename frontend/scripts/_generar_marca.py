"""Genera los activos de marca (logo transparente, variante para fondo oscuro
y favicons) a partir de frontend/src/logo.png. Script puntual, no forma parte
del build; se ejecuta una vez y sus salidas se versionan.

Logo Flexómetro (reemplaza al de Obrai): mismo esquema de dos tintas
(marino + ocre), pero el favicon ya no es una letra suelta — es el propio
glifo de la cinta métrica (el círculo con la muesca y el tirador ocre) que
forma la "Ó" del logotipo, así que conserva sus dos colores en vez de
reducirse a un monocromo sobre fondo marino como antes."""

import numpy as np
from PIL import Image

SRC = "src/logo.png"
# Muestreados del propio logo.png (k-means de 2 clases sobre los píxeles de
# tinta) — no son los mismos valores exactos que el logo anterior de Obrai,
# aunque la paleta (marino + ocre) es deliberadamente parecida.
NAVY = np.array([31, 40, 46], dtype=float)
OCHRE = np.array([233, 183, 51], dtype=float)
OCHRE_STRONG = (248, 180, 8)


UMBRAL_FONDO = 30  # por debajo de esto, el ruido de compresión del PNG
# original (blanco no perfectamente uniforme) se trata como fondo, no tinta.


def cargar_transparente():
    im = Image.open(SRC).convert("RGB")
    arr = np.asarray(im, dtype=float)  # H,W,3, observado sobre fondo blanco

    alpha = 255 - arr.min(axis=2)  # blanco->0, tinta->alto
    # Corte duro por debajo del umbral (ruido de fondo) y reescalado del resto
    # a 0-255, para que el degradado suave quede solo en el borde real de
    # cada letra, no disperso como ruido por todo el fondo.
    alpha = np.where(alpha < UMBRAL_FONDO, 0, alpha)
    alpha = np.clip((alpha - UMBRAL_FONDO) * (255.0 / (255 - UMBRAL_FONDO)), 0, 255)
    alpha_frac = np.clip(alpha / 255.0, 0.001, 1.0)

    # Recupera el color real de la tinta deshaciendo el mezclado con blanco:
    # observado = frac*color + (1-frac)*255  =>  color = (observado-(1-frac)*255)/frac
    true_color = (arr - (1 - alpha_frac[..., None]) * 255.0) / alpha_frac[..., None]
    true_color = np.clip(true_color, 0, 255)
    # Donde no hay tinta, el color es irrelevante (alpha 0) pero se deja un
    # valor neutro para que ningún visor muestre un halo de color falso.
    true_color = np.where(alpha[..., None] == 0, 255.0, true_color)

    return true_color, alpha.astype(np.uint8)


def guardar(rgb: np.ndarray, alpha: np.ndarray, ruta: str) -> None:
    rgba = np.dstack([rgb.astype(np.uint8), alpha])
    Image.fromarray(rgba, mode="RGBA").save(ruta)


def variante_color(true_color, alpha):
    """Logo tal cual (marino + ocre) con fondo transparente, para superficies claras."""
    guardar(true_color, alpha, "src/assets/logo.png")


def variante_clara(true_color, alpha):
    """Marino -> blanco, ocre se mantiene: para la barra lateral marino oscuro."""
    dist_navy = np.linalg.norm(true_color - NAVY, axis=2)
    dist_ochre = np.linalg.norm(true_color - OCHRE, axis=2)
    es_navy = dist_navy < dist_ochre

    out = true_color.copy()
    out[es_navy] = [255, 255, 255]
    out[~es_navy] = OCHRE_STRONG
    guardar(out, alpha, "src/assets/logo-sobre-oscuro.png")


def favicon(true_color, alpha):
    """Recorta el glifo de la cinta métrica (la "Ó" del logo) y lo monta sobre
    un lienzo blanco con esquinas redondeadas — a diferencia del favicon
    anterior (una "O" monocroma sobre fondo marino), este glifo ya tiene sus
    dos tintas propias (marino + ocre), así que se conservan tal cual en vez
    de recolorear nada."""
    x0, x1 = 718, 912
    y0, y1 = 344, 533

    recorte_color = true_color[y0:y1, x0:x1]
    recorte_alpha = alpha[y0:y1, x0:x1]

    lado = max(x1 - x0, y1 - y0)
    pad = int(lado * 0.22)
    canvas_lado = lado + pad * 2

    lienzo = np.full((canvas_lado, canvas_lado, 4), 255, dtype=np.uint8)
    lienzo[..., 3] = 255

    oy = (canvas_lado - (y1 - y0)) // 2
    ox = (canvas_lado - (x1 - x0)) // 2
    region = lienzo[oy : oy + (y1 - y0), ox : ox + (x1 - x0), :3].astype(float)

    frac = (recorte_alpha[..., None].astype(float)) / 255.0
    region[:] = frac * recorte_color + (1 - frac) * region
    lienzo[oy : oy + (y1 - y0), ox : ox + (x1 - x0), :3] = region.astype(np.uint8)

    # Esquinas redondeadas.
    base = Image.fromarray(lienzo, mode="RGBA")
    radio = int(canvas_lado * 0.22)
    mask = Image.new("L", (canvas_lado, canvas_lado), 0)
    from PIL import ImageDraw

    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, canvas_lado - 1, canvas_lado - 1], radius=radio, fill=255)
    base.putalpha(mask)

    tamanos = [16, 32, 48, 64, 180, 192, 512]
    for t in tamanos:
        redim = base.resize((t, t), Image.LANCZOS)
        if t == 180:
            fondo = Image.new("RGB", redim.size, (255, 255, 255))
            fondo.paste(redim, mask=redim.split()[-1])
            fondo.save("public/apple-touch-icon.png")
        elif t == 192:
            redim.save("public/icon-192.png")
        elif t == 512:
            redim.save("public/icon-512.png")
        else:
            redim.save(f"public/favicon-{t}.png")

    # .ico multi-resolución con los tamaños clásicos de pestaña/barra de tareas.
    base.resize((256, 256), Image.LANCZOS).save(
        "public/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)]
    )


if __name__ == "__main__":
    true_color, alpha = cargar_transparente()
    variante_color(true_color, alpha)
    variante_clara(true_color, alpha)
    favicon(true_color, alpha)
    print("OK: activos de marca generados")
