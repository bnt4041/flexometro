"""Generación de un fichero BC3 a partir de un presupuesto.

Se emite en cp1252 (lo que la norma llama ANSI) por compatibilidad: es lo que
esperan Presto y Arquímedes por defecto. Se puede pedir UTF-8, que la norma
admite desde FIEBDC-3/2012, cuando el destino se sepa moderno.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenancy import require_organization_id
from app.modules.presupuestos.models import Concepto, Descomposicion, TipoConcepto
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    LineaMedicion,
    Partida,
    Presupuesto,
)

VERSION = "FIEBDC-3/2016"
EMISOR = "Obras"

# Naturaleza del concepto -> campo TIPO del registro ~C.
TIPO_FIEBDC = {
    "sin_clasificar": "0",
    "mano_obra": "1",
    "maquinaria": "2",
    "material": "3",
    "residuo": "4",
    "otro": "0",
}


def _limpiar(texto: str | None) -> str:
    """Quita los caracteres que estructuran el formato.

    `|`, `\\` y `~` son separadores; si se cuelan dentro de una descripción
    parten el registro y el fichero deja de ser legible para el otro programa.
    Se sustituyen por espacio, que es lo que hacen los exportadores comerciales.
    """
    if not texto:
        return ""
    limpio = texto.replace("|", " ").replace("\\", " ").replace("~", " ")
    return " ".join(limpio.split())


def _numero(valor: Decimal | None, decimales: int = 2) -> str:
    if valor is None:
        return ""
    return f"{Decimal(valor):.{decimales}f}"


def _fecha(valor: date | None) -> str:
    return valor.strftime("%d%m%Y") if valor else ""


async def exportar_presupuesto(
    session: AsyncSession,
    presupuesto: Presupuesto,
    *,
    codificacion: str = "cp1252",
) -> bytes:
    org_id = require_organization_id()

    capitulos = list(
        (
            await session.execute(
                select(Capitulo)
                .where(Capitulo.presupuesto_id == presupuesto.id)
                .order_by(Capitulo.orden, Capitulo.codigo)
            )
        ).scalars()
    )
    partidas = list(
        (
            await session.execute(
                select(Partida)
                .where(Partida.presupuesto_id == presupuesto.id)
                .order_by(Partida.orden)
            )
        ).scalars()
    )
    lineas_medicion: dict[uuid.UUID, list[LineaMedicion]] = {}
    for linea in (
        await session.execute(
            select(LineaMedicion)
            .join(Partida, Partida.id == LineaMedicion.partida_id)
            .where(Partida.presupuesto_id == presupuesto.id)
            .order_by(LineaMedicion.orden)
        )
    ).scalars():
        lineas_medicion.setdefault(linea.partida_id, []).append(linea)

    # Los precios del presupuesto se exportan con su descomposición, para que
    # el fichero sea autosuficiente y el destino pueda reconstruir el cuadro.
    conceptos = await _conceptos_implicados(session, partidas, org_id)

    lineas: list[str] = []
    codigo_raiz = f"{presupuesto.codigo}##"
    hoy = date.today().strftime("%d/%m/%Y")
    juego = "UTF-8" if codificacion.lower().replace("-", "") == "utf8" else "ANSI"

    lineas.append(
        f"~V|{_limpiar(presupuesto.nombre)}|{VERSION}\\{hoy}|{EMISOR}|"
        f"{_limpiar(presupuesto.nombre)}|{juego}||"
    )

    # --- Conceptos ---

    lineas.append(
        f"~C|{codigo_raiz}||{_limpiar(presupuesto.nombre)}|0|{_fecha(presupuesto.fecha)}|0|"
    )

    for capitulo in capitulos:
        lineas.append(f"~C|{capitulo.codigo}#||{_limpiar(capitulo.resumen)}|0||0|")
        if capitulo.texto:
            lineas.append(f"~T|{capitulo.codigo}#|{_limpiar(capitulo.texto)}|")

    for concepto in conceptos.values():
        tipo = TIPO_FIEBDC.get(concepto.naturaleza.value, "0")
        lineas.append(
            f"~C|{concepto.codigo}|{_limpiar(concepto.unidad)}|{_limpiar(concepto.resumen)}"
            f"|{_numero(concepto.precio)}|{_fecha(concepto.fecha_precio)}|{tipo}|"
        )
        if concepto.texto:
            lineas.append(f"~T|{concepto.codigo}|{_limpiar(concepto.texto)}|")

    # Las partidas alzadas no están en el cuadro de precios, así que se emiten
    # como conceptos propios o el fichero quedaría con referencias colgando.
    for partida in partidas:
        if partida.concepto_id is None or partida.concepto_id not in conceptos:
            lineas.append(
                f"~C|{partida.codigo}|{_limpiar(partida.unidad)}|{_limpiar(partida.resumen)}"
                f"|{_numero(partida.precio)}||0|"
            )

    # --- Estructura ---

    hijos_de_capitulo: dict[uuid.UUID | None, list[Capitulo]] = {}
    for capitulo in capitulos:
        hijos_de_capitulo.setdefault(capitulo.parent_id, []).append(capitulo)
    partidas_de: dict[uuid.UUID, list[Partida]] = {}
    for partida in partidas:
        partidas_de.setdefault(partida.capitulo_id, []).append(partida)

    raices = hijos_de_capitulo.get(None, [])
    if raices:
        hijos = "\\".join(f"{c.codigo}#\\1\\1" for c in raices)
        lineas.append(f"~D|{codigo_raiz}|{hijos}|")

    for capitulo in capitulos:
        elementos: list[str] = []
        for hijo in hijos_de_capitulo.get(capitulo.id, []):
            elementos.append(f"{hijo.codigo}#\\1\\1")
        for partida in partidas_de.get(capitulo.id, []):
            elementos.append(f"{partida.codigo}\\1\\{_numero(partida.medicion, 3)}")
        if elementos:
            lineas.append(f"~D|{capitulo.codigo}#|{'\\'.join(elementos)}|")

    # Descomposición de los precios del cuadro.
    for concepto in conceptos.values():
        if not concepto.lineas:
            continue
        elementos = [
            f"{linea.hijo.codigo}\\{_numero(linea.factor, 6)}\\{_numero(linea.rendimiento, 6)}"
            for linea in concepto.lineas
        ]
        lineas.append(f"~D|{concepto.codigo}|{'\\'.join(elementos)}|")

    # --- Mediciones ---

    codigo_capitulo = {c.id: c.codigo for c in capitulos}
    for partida in partidas:
        filas = lineas_medicion.get(partida.id, [])
        if not filas:
            continue
        grupos = "".join(
            "\\".join(
                [
                    "",
                    _limpiar(fila.comentario),
                    _numero(fila.uds, 3),
                    _numero(fila.longitud, 3),
                    _numero(fila.anchura, 3),
                    _numero(fila.altura, 3),
                ]
            )
            + "\\"
            for fila in filas
        )
        padre = codigo_capitulo.get(partida.capitulo_id, "")
        lineas.append(
            f"~M|{padre}#\\{partida.codigo}|1|{_numero(partida.medicion, 3)}|{grupos}|"
        )

    texto = "\r\n".join(lineas) + "\r\n"
    # errors="replace": un carácter fuera de cp1252 no puede impedir exportar.
    return texto.encode(codificacion, errors="replace")


async def _conceptos_implicados(
    session: AsyncSession, partidas: list[Partida], org_id: uuid.UUID
) -> dict[uuid.UUID, Concepto]:
    """Conceptos usados por las partidas y, recursivamente, sus componentes."""
    pendientes = {p.concepto_id for p in partidas if p.concepto_id is not None}
    recogidos: dict[uuid.UUID, Concepto] = {}

    while pendientes:
        filas = (
            await session.execute(
                select(Concepto)
                .options(selectinload(Concepto.lineas).selectinload(Descomposicion.hijo))
                .where(Concepto.id.in_(pendientes), Concepto.organization_id == org_id)
            )
        ).scalars()

        siguientes: set[uuid.UUID] = set()
        for concepto in filas:
            recogidos[concepto.id] = concepto
            for linea in concepto.lineas:
                if linea.hijo_id not in recogidos:
                    siguientes.add(linea.hijo_id)
        pendientes = siguientes

    # Se emiten de básicos a unitarios: leído por un humano, el fichero cuenta
    # la cadena de precios en el orden en que se construye.
    orden = {TipoConcepto.BASICO: 0, TipoConcepto.AUXILIAR: 1, TipoConcepto.UNITARIO: 2}
    return dict(
        sorted(
            recogidos.items(),
            key=lambda par: (orden.get(par[1].tipo, 3), par[1].codigo),
        )
    )
