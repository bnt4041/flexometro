"""Leer un DXF y dejarlo en trazos que se puedan pintar y medir.

Un DXF no se rasteriza: se aplana. Cada entidad —línea, arco, círculo,
polilínea, spline— se convierte en una lista de puntos, y esa lista es a la
vez lo que se dibuja en pantalla y lo que se mide. Por eso medir sobre un DXF
es exacto y medir sobre un PDF escaneado no lo es: aquí no se estima dónde
está la pared, se sabe.

Dos cosas que este módulo hace y que no son obvias:

**Los bloques se explotan.** Un plano real mete puertas, ventanas y mobiliario
como referencias a bloques (`INSERT`). Sin explotarlos, el plano se vería
medio vacío y faltaría justo lo que se quiere contar.

**El eje Y se le da la vuelta.** En DXF la Y crece hacia arriba y en pantalla
crece hacia abajo. Sin invertirlo, el plano sale del revés — y con las cotas
al revés nadie se daría cuenta hasta haber medido mal.
"""

import io
import logging
import math
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)


class DxfInvalido(Exception):
    pass


#: Cuánto se permite que un arco se aparte de la cuerda al aproximarlo por
#: segmentos, en unidades del dibujo. Con esto un círculo de un metro sale con
#: unas decenas de segmentos: ni pesa ni se ve poligonal.
FLECHA = 0.5

#: Tope de trazos. Un plano de arquitectura completo anda por los miles; cien
#: mil es un fichero equivocado, y además el navegador no puede con eso. Se
#: rechaza entero en vez de importar la mitad: medio plano es peor que ninguno,
#: porque no se nota.
MAX_TRAZOS = 60_000

#: `$INSUNITS` -> metros por unidad de dibujo. Un DXF suele decir en qué
#: unidades está, así que no hace falta calibrarlo a mano: es la ventaja de
#: verdad frente a un plano escaneado.
UNIDADES = {
    1: Decimal("0.0254"),      # pulgadas
    2: Decimal("0.3048"),      # pies
    4: Decimal("0.001"),       # milímetros
    5: Decimal("0.01"),        # centímetros
    6: Decimal("1"),           # metros
    14: Decimal("0.1"),        # decímetros
    21: Decimal("0.3048006096012192"),  # pies topográficos
}


@dataclass
class Trazo:
    capa: str
    puntos: list[tuple[float, float]]
    cerrado: bool = False


@dataclass
class Dibujo:
    trazos: list[Trazo] = field(default_factory=list)
    capas: list[str] = field(default_factory=list)
    ancho: float = 0.0
    alto: float = 0.0
    #: Metros por unidad del dibujo, si el fichero lo declara. `None` obliga a
    #: calibrar a mano, igual que un PDF.
    metros_por_unidad: Decimal | None = None
    #: Lo que se ha dejado fuera, para poder decirlo en vez de callarlo.
    omitidas: dict[str, int] = field(default_factory=dict)


def leer(contenido: bytes) -> Dibujo:
    """De los bytes del fichero a trazos en coordenadas de hoja."""
    import ezdxf
    from ezdxf.recover import read as recuperar

    try:
        # `recover` en vez de `read`: los DXF que salen de AutoCAD y de sus
        # imitadores traen defectos que la lectura estricta rechaza, y son
        # ficheros perfectamente utilizables.
        doc, auditoria = recuperar(io.BytesIO(contenido))
    except (ezdxf.DXFError, OSError, UnicodeDecodeError) as exc:
        raise DxfInvalido(f"No se ha podido leer el DXF: {exc}") from exc
    if auditoria.has_errors:
        logger.info("DXF con %d defectos recuperados", len(auditoria.errors))

    crudos, omitidas = _aplanar(doc)
    if not crudos:
        raise DxfInvalido("El DXF no tiene ninguna geometría que se pueda dibujar")
    if len(crudos) > MAX_TRAZOS:
        raise DxfInvalido(
            f"El DXF tiene {len(crudos)} elementos y el tope está en {MAX_TRAZOS}. "
            "Prueba a purgar capas que no necesites antes de subirlo."
        )

    dibujo = _encajar(crudos)
    dibujo.omitidas = omitidas
    dibujo.metros_por_unidad = _escala(doc)
    return dibujo


def _aplanar(doc) -> tuple[list[Trazo], dict[str, int]]:
    from ezdxf import path as rutas

    trazos: list[Trazo] = []
    omitidas: dict[str, int] = {}

    def recorrer(entidades, heredada: str | None = None, profundidad: int = 0) -> None:
        # Un bloque puede contener otro bloque. Sin tope, un fichero con una
        # referencia circular colgaría el proceso.
        if profundidad > 4:
            return
        for entidad in entidades:
            tipo = entidad.dxftype()
            propia = str(getattr(entidad.dxf, "layer", "0"))
            # Regla de DXF: lo que está en la capa «0» dentro de un bloque
            # hereda la capa de la referencia que lo inserta. Sin esto, las
            # puertas y el mobiliario acaban todos en la capa «0» y apagar su
            # capa de verdad no los oculta — que es justo para lo que sirven
            # las capas.
            capa = heredada if (propia == "0" and heredada) else propia
            try:
                if tipo == "INSERT":
                    recorrer(entidad.virtual_entities(), capa, profundidad + 1)
                    continue
                if tipo == "POINT":
                    p = entidad.dxf.location
                    trazos.append(Trazo(capa, [(float(p.x), float(p.y))]))
                    continue
                camino = rutas.make_path(entidad)
                puntos = [(float(v.x), float(v.y)) for v in camino.flattening(FLECHA)]
                if len(puntos) >= 2:
                    trazos.append(
                        Trazo(capa, puntos, cerrado=bool(getattr(camino, "is_closed", False)))
                    )
            except Exception:  # noqa: BLE001
                # Texto, cotas, sombreados, tablas... no son geometría medible.
                # Se cuentan para poder decir qué se ha quedado fuera, en vez
                # de hacer como que el plano estaba completo.
                omitidas[tipo] = omitidas.get(tipo, 0) + 1

    recorrer(doc.modelspace())
    return trazos, omitidas


def _encajar(trazos: list[Trazo]) -> Dibujo:
    """Lleva el dibujo al primer cuadrante y le da la vuelta a la Y.

    El origen del DXF puede estar en cualquier parte (coordenadas UTM, por
    ejemplo), así que se traslada para que la hoja empiece en 0,0. Trasladar y
    reflejar no cambian ninguna distancia ni ningún área, que es lo único que
    importa aquí.
    """
    xs = [p[0] for t in trazos for p in t.puntos]
    ys = [p[1] for t in trazos for p in t.puntos]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    ancho, alto = x1 - x0, y1 - y0
    if not math.isfinite(ancho) or not math.isfinite(alto) or ancho <= 0 or alto <= 0:
        raise DxfInvalido("El DXF no tiene extensión: toda la geometría cae en un punto")

    # Un margen del 1 % para que lo que toca el borde no quede pegado al canto.
    margen = max(ancho, alto) * 0.01
    movidos = [
        Trazo(
            t.capa,
            [(p[0] - x0 + margen, (y1 - p[1]) + margen) for p in t.puntos],
            t.cerrado,
        )
        for t in trazos
    ]
    capas = sorted({t.capa for t in movidos})
    return Dibujo(
        trazos=movidos, capas=capas, ancho=ancho + margen * 2, alto=alto + margen * 2
    )


def _escala(doc) -> Decimal | None:
    try:
        codigo = int(doc.header.get("$INSUNITS", 0))
    except (TypeError, ValueError):
        return None
    return UNIDADES.get(codigo)


def a_json(dibujo: Dibujo) -> dict:
    """Lo que se guarda en la hoja y viaja al navegador.

    Los puntos van como pares y no como `{"x":…,"y":…}`: en un plano de veinte
    mil trazos, las claves repetidas multiplican por tres lo que se manda por
    el cable sin añadir nada.
    """
    return {
        "capas": dibujo.capas,
        "trazos": [
            {
                "c": t.capa,
                "p": [[round(x, 4), round(y, 4)] for x, y in t.puntos],
                **({"z": True} if t.cerrado else {}),
            }
            for t in dibujo.trazos
        ],
        "omitidas": dibujo.omitidas,
    }
