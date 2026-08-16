"""Parseo de los registros BC3 al modelo intermedio.

Se leen los registros que hacen falta para reconstruir un banco de precios o un
presupuesto: ~V (cabecera), ~C (conceptos), ~D (descomposición), ~T (textos) y
~M (mediciones). El resto se cuenta como incidencia informativa y no se pierde
de vista, pero no impide importar.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.modules.presupuestos.fiebdc.lector import (
    decodificar,
    detectar_codificacion,
    leer_registros,
)
from app.modules.presupuestos.fiebdc.modelo import (
    ArchivoBC3,
    ConceptoBC3,
    Incidencia,
    LineaDescomposicion,
    LineaMedicion,
    Medicion,
    TipoConceptoBC3,
)

# Registros que se entienden. Los demás se anotan como incidencia.
REGISTROS_SOPORTADOS = {"V", "C", "D", "T", "M", "K"}


def a_decimal(texto: str, por_defecto: Decimal | None = None) -> Decimal | None:
    """Número de un campo BC3.

    La norma usa el punto como separador decimal, pero hay ficheros con coma;
    se aceptan los dos porque rechazarlos no aporta nada.
    """
    valor = (texto or "").strip()
    if not valor:
        return por_defecto
    if "," in valor and "." not in valor:
        valor = valor.replace(",", ".")
    try:
        return Decimal(valor)
    except InvalidOperation:
        return por_defecto


_RE_FECHA = re.compile(r"^\d{8}$")


def a_fecha(texto: str) -> date | None:
    """Fecha de ocho dígitos.

    Conviven `DDMMAAAA` y `AAAAMMDD` según el programa que generó el fichero,
    así que se decide por el bloque que parece un año. Si no cuadra, se deja a
    nulo: una fecha dudosa no vale la pena romper una importación.
    """
    valor = (texto or "").strip().replace("/", "").replace("-", "")
    if not _RE_FECHA.match(valor):
        return None
    try:
        if valor[:2] in ("19", "20"):
            return date(int(valor[:4]), int(valor[4:6]), int(valor[6:8]))
        return date(int(valor[4:8]), int(valor[2:4]), int(valor[:2]))
    except ValueError:
        return None


def es_capitulo(codigo: str) -> bool:
    """Los códigos de capítulo terminan en '#', y el de la obra en '##'."""
    return codigo.endswith("#")


def es_raiz(codigo: str) -> bool:
    return codigo.endswith("##")


def parsear(datos: bytes) -> ArchivoBC3:
    archivo = ArchivoBC3(codificacion=detectar_codificacion(datos))
    texto = decodificar(datos)

    for registro in leer_registros(texto):
        if registro.tipo == "V":
            _leer_cabecera(archivo, registro)
        elif registro.tipo == "C":
            _leer_conceptos(archivo, registro)
        elif registro.tipo == "D":
            _leer_descomposicion(archivo, registro)
        elif registro.tipo == "T":
            _leer_texto(archivo, registro)
        elif registro.tipo == "M":
            _leer_medicion(archivo, registro)
        elif registro.tipo == "K":
            pass  # coeficientes y decimales: no alteran lo que importamos
        elif registro.tipo:
            archivo.incidencias.append(
                Incidencia(
                    linea=registro.linea,
                    registro=f"~{registro.tipo}",
                    detalle="Tipo de registro no interpretado; se ignora",
                )
            )

    _clasificar(archivo)
    return archivo


def _leer_cabecera(archivo: ArchivoBC3, registro) -> None:
    # ~V | propiedad | version\fecha | programa | cabecera | juego_caracteres | ...
    version = registro.subcampos(1)
    archivo.version = version[0] if version else ""
    archivo.fecha = version[1] if len(version) > 1 else ""
    archivo.programa = registro.campo(2)
    archivo.cabecera = registro.campo(3)


def _leer_conceptos(archivo: ArchivoBC3, registro) -> None:
    """~C | CODIGO{\\CODIGO} | UNIDAD | RESUMEN | PRECIO{\\PRECIO} | FECHA{\\FECHA} | TIPO |

    Un mismo registro puede declarar varios códigos que comparten propiedades.
    """
    codigos = [c.strip() for c in registro.subcampos(0) if c.strip()]
    if not codigos:
        archivo.incidencias.append(
            Incidencia(registro.linea, "~C", "Registro de concepto sin código")
        )
        return

    unidad = registro.campo(1)
    resumen = registro.campo(2)
    precios = registro.subcampos(3)
    fechas = registro.subcampos(4)
    tipo_fiebdc = registro.campo(5)

    # Puede haber varias columnas de precio; se toma la primera, que es el
    # precio vigente. Las demás son revisiones y no tienen sitio en el modelo.
    precio = a_decimal(precios[0], Decimal("0")) if precios else Decimal("0")
    fecha = a_fecha(fechas[0]) if fechas else None

    for codigo in codigos:
        existente = archivo.conceptos.get(codigo)
        if existente is not None:
            # Redefinir un concepto es legal: gana lo último informado.
            existente.unidad = unidad or existente.unidad
            existente.resumen = resumen or existente.resumen
            if precio:
                existente.precio = precio
            existente.fecha = fecha or existente.fecha
            existente.tipo_fiebdc = tipo_fiebdc or existente.tipo_fiebdc
            continue

        archivo.conceptos[codigo] = ConceptoBC3(
            codigo=codigo,
            unidad=unidad,
            resumen=resumen,
            precio=precio or Decimal("0"),
            fecha=fecha,
            tipo_fiebdc=tipo_fiebdc,
        )


def _leer_descomposicion(archivo: ArchivoBC3, registro) -> None:
    """~D | CODIGO_PADRE | HIJO\\FACTOR\\RENDIMIENTO{\\HIJO\\FACTOR\\RENDIMIENTO} |"""
    padre = registro.campo(0)
    if not padre:
        archivo.incidencias.append(
            Incidencia(registro.linea, "~D", "Descomposición sin concepto padre")
        )
        return

    partes = registro.subcampos(1)
    lineas: list[LineaDescomposicion] = []
    for i in range(0, len(partes), 3):
        grupo = partes[i : i + 3]
        hijo = grupo[0].strip() if grupo else ""
        if not hijo:
            continue
        if len(grupo) < 3:
            archivo.incidencias.append(
                Incidencia(
                    registro.linea,
                    "~D",
                    f"Línea incompleta para '{hijo}'; se asume factor 1 y rendimiento 0",
                )
            )
        lineas.append(
            LineaDescomposicion(
                hijo=hijo,
                factor=a_decimal(grupo[1] if len(grupo) > 1 else "", Decimal("1"))
                or Decimal("1"),
                rendimiento=a_decimal(grupo[2] if len(grupo) > 2 else "", Decimal("0"))
                or Decimal("0"),
            )
        )

    if lineas:
        archivo.descomposiciones.setdefault(padre, []).extend(lineas)


def _leer_texto(archivo: ArchivoBC3, registro) -> None:
    """~T | CODIGO | TEXTO |"""
    codigo = registro.campo(0)
    if not codigo:
        return
    # El texto puede traer '|' escapados o saltos de línea; se conserva crudo.
    texto = registro.campo(1)
    concepto = archivo.conceptos.get(codigo)
    if concepto is not None:
        concepto.texto = texto
    else:
        # El texto puede venir antes que su ~C; se crea el hueco.
        archivo.conceptos[codigo] = ConceptoBC3(codigo=codigo, texto=texto)


def _leer_medicion(archivo: ArchivoBC3, registro) -> None:
    """~M | PADRE\\HIJO | POSICION | TOTAL | {TIPO\\COMENTARIO\\UDS\\LONG\\LAT\\ALT} | ETIQUETA |

    Las líneas de medición van en grupos de seis subcampos.
    """
    ruta = registro.subcampos(0)
    if not ruta:
        archivo.incidencias.append(
            Incidencia(registro.linea, "~M", "Medición sin concepto asociado")
        )
        return
    padre = ruta[0].strip() if len(ruta) > 1 else ""
    hijo = ruta[1].strip() if len(ruta) > 1 else ruta[0].strip()

    medicion = Medicion(padre=padre, hijo=hijo, total=a_decimal(registro.campo(2)))

    partes = registro.subcampos(3)
    for i in range(0, len(partes), 6):
        grupo = partes[i : i + 6]
        if not any(g.strip() for g in grupo):
            continue
        # grupo = [tipo, comentario, uds, longitud, latitud, altura]
        medicion.lineas.append(
            LineaMedicion(
                comentario=(grupo[1].strip() if len(grupo) > 1 else ""),
                uds=a_decimal(grupo[2] if len(grupo) > 2 else ""),
                longitud=a_decimal(grupo[3] if len(grupo) > 3 else ""),
                anchura=a_decimal(grupo[4] if len(grupo) > 4 else ""),
                altura=a_decimal(grupo[5] if len(grupo) > 5 else ""),
            )
        )

    archivo.mediciones.append(medicion)


def _clasificar(archivo: ArchivoBC3) -> None:
    """Asigna a cada concepto su nivel en la cadena de precios.

    El sufijo del código resuelve raíz y capítulos, que es la parte de la
    convención que todos los bancos respetan. Para el resto manda la
    estructura: sin descomposición es un básico; con descomposición, es
    unitario si cuelga de un capítulo y auxiliar si solo lo usan otros
    conceptos. Un auxiliar es, por definición, un descompuesto que entra
    dentro de otro descompuesto.
    """
    padres_de: dict[str, set[str]] = {}
    for padre, lineas in archivo.descomposiciones.items():
        for linea in lineas:
            padres_de.setdefault(linea.hijo, set()).add(padre)

    for codigo, concepto in archivo.conceptos.items():
        if es_raiz(codigo):
            concepto.tipo = TipoConceptoBC3.RAIZ
            continue
        if es_capitulo(codigo):
            concepto.tipo = TipoConceptoBC3.CAPITULO
            continue
        if codigo not in archivo.descomposiciones:
            concepto.tipo = TipoConceptoBC3.BASICO
            continue

        padres = padres_de.get(codigo, set())
        cuelga_de_capitulo = any(es_capitulo(p) for p in padres)
        usado_por_otro_precio = any(not es_capitulo(p) for p in padres)

        if cuelga_de_capitulo or not usado_por_otro_precio:
            # Sin padres tampoco es auxiliar: es un precio de primer nivel.
            concepto.tipo = TipoConceptoBC3.UNITARIO
        else:
            concepto.tipo = TipoConceptoBC3.AUXILIAR
