"""Lectura de bajo nivel de un fichero FIEBDC-3 (BC3).

El formato es texto plano con registros que empiezan por `~` a principio de
línea, campos separados por `|` y subcampos por `\\`. Un registro puede ocupar
varias líneas: mientras la siguiente no empiece por `~`, es continuación.

El detalle incómodo es la codificación: la declara el propio fichero en el
registro ~V, así que hay que leer ese registro antes de saber cómo decodificar
el resto. Se resuelve decodificando la cabecera con latin-1 —que nunca falla,
porque asigna un carácter a cada uno de los 256 bytes— para leer la
declaración, y decodificando después el fichero entero con la buena.
"""

from dataclasses import dataclass
from typing import Iterator

# Lo que el registro ~V puede declarar, y su códec en Python.
CODIFICACIONES = {
    "ANSI": "cp1252",
    "WINDOWS-1252": "cp1252",
    "ISO-8859-1": "iso-8859-1",
    "LATIN1": "iso-8859-1",
    "850": "cp850",
    "OEM": "cp850",
    "437": "cp437",
    "UTF-8": "utf-8",
    "UTF8": "utf-8",
}
CODIFICACION_POR_DEFECTO = "cp1252"


@dataclass
class Registro:
    """Un registro del fichero, ya troceado en campos."""

    tipo: str
    campos: list[str]
    linea: int

    def campo(self, indice: int) -> str:
        """Campo por posición, o cadena vacía si el fichero no lo trae.

        Los BC3 reales omiten con frecuencia los campos finales, así que pedir
        uno que no está tiene que ser inocuo y no una excepción.
        """
        if 0 <= indice < len(self.campos):
            return self.campos[indice].strip()
        return ""

    def subcampos(self, indice: int) -> list[str]:
        valor = self.campo(indice)
        return valor.split("\\") if valor else []


def detectar_codificacion(datos: bytes) -> str:
    """Códec declarado en el registro ~V, o cp1252 si no lo dice.

    cp1252 por defecto porque es lo que emiten Presto y Arquímedes cuando no
    declaran nada; suponer UTF-8 rompería todas las tildes.
    """
    cabecera = datos[:4096].decode("latin-1", errors="replace")
    for linea in cabecera.splitlines():
        if not linea.startswith("~V"):
            continue
        campos = linea.split("|")
        # ~V | propiedad | version\fecha | programa | cabecera | juego_caracteres | ...
        if len(campos) > 5:
            declarado = campos[5].strip().upper()
            if declarado in CODIFICACIONES:
                return CODIFICACIONES[declarado]
        break

    # Sin declaración: si el fichero es UTF-8 válido y trae multibyte, lo es.
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError:
        return CODIFICACION_POR_DEFECTO
    return "utf-8" if any(ord(c) > 127 for c in texto) else CODIFICACION_POR_DEFECTO


def decodificar(datos: bytes) -> str:
    codec = detectar_codificacion(datos)
    # errors="replace": un byte suelto corrupto no puede tirar una importación
    # de treinta mil conceptos.
    return datos.decode(codec, errors="replace")


def leer_registros(texto: str) -> Iterator[Registro]:
    """Trocea el texto en registros, uniendo las líneas de continuación."""
    acumulado: list[str] = []
    linea_inicio = 0

    def emitir() -> Registro | None:
        if not acumulado:
            return None
        crudo = "\n".join(acumulado)
        # Se quita el '~' inicial y se parte por campos.
        campos = crudo[1:].split("|")
        tipo = campos[0].strip().upper() if campos else ""
        return Registro(tipo=tipo, campos=[c for c in campos[1:]], linea=linea_inicio)

    for numero, linea in enumerate(texto.splitlines(), start=1):
        if linea.startswith("~"):
            registro = emitir()
            if registro is not None:
                yield registro
            acumulado = [linea.rstrip("\r")]
            linea_inicio = numero
        elif acumulado:
            acumulado.append(linea.rstrip("\r"))
        # Lo que aparezca antes del primer '~' se ignora: hay ficheros con
        # una línea de cortesía del programa que los generó.

    registro = emitir()
    if registro is not None:
        yield registro
