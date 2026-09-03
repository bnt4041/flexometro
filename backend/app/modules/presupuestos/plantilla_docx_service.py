"""Plantillas Word: subir, listar, borrar, y rellenar con los datos de un
presupuesto para descargar en Word o PDF.

`docxtpl` (Jinja2 sobre `python-docx`) es el motor de relleno — las mismas
claves `{{ }}` que ya usa el resto de la app para HTML, pero dentro de un
`.docx` en vez de una plantilla en el repo. La conversión a PDF pasa por
LibreOffice en modo headless (Fase 39): no hay librería Python que convierta
DOCX→PDF con fidelidad, así que se invoca `soffice` como subproceso.
"""

import asyncio
import copy
import logging
import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docxtpl import DocxTemplate
from jinja2 import Environment, TemplateSyntaxError
from lxml import etree
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.tenancy import datos_autoria
from app.modules.core import service as core_service
from app.modules.presupuestos import datos_exportacion as datos
from app.modules.presupuestos.models_presupuesto import Presupuesto
from app.modules.presupuestos.plantilla_docx_models import PlantillaPresupuesto

logger = logging.getLogger("obras")

DIRECTORIO_SISTEMA = Path(__file__).parent / "plantillas_docx_defecto"
# (nombre visible, fichero, clave del objeto en MinIO)
PLANTILLAS_SISTEMA = [
    ("Presupuesto", "presupuesto.docx", "sistema/presupuesto.docx"),
    ("Mediciones", "mediciones.docx", "sistema/mediciones.docx"),
    ("Descompuestos", "descompuestos.docx", "sistema/descompuestos.docx"),
]

TIMEOUT_CONVERSION_SEGUNDOS = 30


class PlantillaInvalida(Exception):
    """Lleva el error en dos niveles: `mensaje_usuario` (qué ha pasado y qué
    hacer, en lenguaje llano) y `nota_tecnica` (el detalle real — excepción,
    línea, etiqueta concreta — para quien construyó la plantilla o para
    soporte). `reparable` marca los casos que `reparar_tags_docxtpl()` sabe
    arreglar solo, para que la pantalla pueda ofrecer ese botón."""

    def __init__(self, mensaje_usuario: str, nota_tecnica: str = "", reparable: bool = False):
        super().__init__(mensaje_usuario)
        self.mensaje_usuario = mensaje_usuario
        self.nota_tecnica = nota_tecnica or mensaje_usuario
        self.reparable = reparable


class ConversionPdfFallida(Exception):
    pass


def _formato_es(valor: Any, decimales: int = 2) -> str:
    if valor is None:
        return ""
    numero = Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales))
    entero, _, fraccion = f"{abs(numero):.{decimales}f}".partition(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    texto = ".".join(grupos)
    if decimales:
        texto = f"{texto},{fraccion}"
    return f"-{texto}" if numero < 0 else texto


def _entorno_jinja() -> Environment:
    entorno = Environment(autoescape=False)
    entorno.filters["eur"] = lambda v: _formato_es(v, 2)
    entorno.filters["num"] = _formato_es
    return entorno


async def contexto_plantilla(session: AsyncSession, presupuesto: Presupuesto) -> dict[str, Any]:
    """Todas las claves disponibles para una plantilla, en listas planas."""
    cliente = await datos.cliente_de(session, presupuesto)
    capitulos, partidas = await datos.capitulos_y_partidas_planos(
        session, presupuesto.id, con_mediciones=True
    )
    totales = await datos.totales_de(session, presupuesto)
    conceptos = await datos.conceptos_del_presupuesto(session, presupuesto.id)
    organizacion = await core_service.obtener_organizacion(session, presupuesto.organization_id)

    from app.modules.core import tesoreria_service

    cuenta_banco = await tesoreria_service.predeterminada(session)

    return {
        "presupuesto": {
            "codigo": presupuesto.codigo,
            "nombre": presupuesto.nombre,
            "descripcion": presupuesto.descripcion or "",
            "fecha": presupuesto.fecha,
            "emplazamiento": presupuesto.emplazamiento or "",
            "tipo_obra": presupuesto.tipo_obra or "",
            "validez_dias": presupuesto.validez_dias,
            "notas": presupuesto.notas or "",
            "estado": presupuesto.estado.value,
        },
        "cliente": (
            {
                "razon_social": cliente.razon_social,
                "nif": cliente.nif or "",
                "direccion": cliente.direccion or "",
                "codigo_postal": cliente.codigo_postal or "",
                "ciudad": cliente.ciudad or "",
                "provincia": cliente.provincia or "",
                "email": cliente.email or "",
                "telefono": cliente.telefono or "",
            }
            if cliente
            else {}
        ),
        "totales": totales,
        "capitulos": [
            {"codigo": c.codigo, "resumen": c.resumen, "importe": c.importe, "importe_venta": c.importe_venta}
            for c in capitulos
        ],
        "partidas": [
            {
                "capitulo_codigo": p.capitulo_codigo,
                "capitulo_resumen": p.capitulo_resumen,
                "codigo": p.codigo,
                "resumen": p.resumen,
                "texto": p.texto,
                "unidad": p.unidad,
                "medicion": p.medicion,
                "precio": p.precio,
                "precio_venta": p.precio_venta,
                "importe": p.importe,
                "importe_venta": p.importe_venta,
            }
            for p in partidas
        ],
        # Planas también, por la misma razón que capítulos/partidas: una
        # tabla de Word con bucles anidados es frágil de editar a mano.
        "lineas_medicion": [
            {
                "capitulo_codigo": p.capitulo_codigo,
                "partida_codigo": p.codigo,
                "partida_resumen": p.resumen,
                "comentario": linea.comentario or "",
                "uds": linea.uds,
                "longitud": linea.longitud,
                "anchura": linea.anchura,
                "altura": linea.altura,
                "parcial": linea.parcial,
            }
            for p in partidas
            for linea in p.lineas_medicion
        ],
        "conceptos": [
            {"codigo": c.codigo, "resumen": c.resumen, "unidad": c.unidad, "precio": c.precio}
            for c in conceptos
        ],
        # `lineas_informe` son `LineaOut` (service.lineas_de): ya vienen con
        # los datos del hijo aplanados (hijo_codigo/hijo_resumen/...), no un
        # objeto `.hijo` anidado — LineaOut tampoco tiene `.precio` propio,
        # el precio del componente es `hijo_precio`.
        "componentes_descompuesto": [
            {
                "concepto_codigo": c.codigo,
                "concepto_resumen": c.resumen,
                "hijo_codigo": linea.hijo_codigo,
                "hijo_resumen": linea.hijo_resumen,
                "hijo_unidad": linea.hijo_unidad,
                "rendimiento": linea.rendimiento,
                "factor": linea.factor,
                "precio": linea.hijo_precio,
            }
            for c in conceptos
            for linea in getattr(c, "lineas_informe", [])
        ],
        "organizacion": (
            {
                "nombre": organizacion.name,
                "cif": organizacion.cif or "",
                "direccion": organizacion.direccion or "",
                "codigo_postal": organizacion.codigo_postal or "",
                "ciudad": organizacion.ciudad or "",
                "provincia": organizacion.provincia or "",
                "telefono": organizacion.telefono or "",
                "email": organizacion.email or "",
                "web": organizacion.web or "",
                "linkedin": organizacion.linkedin or "",
                "instagram": organizacion.instagram or "",
                "facebook": organizacion.facebook or "",
                "twitter": organizacion.twitter or "",
            }
            if organizacion
            else {}
        ),
        # La cuenta marcada como predeterminada en Ajustes -> Bancos y cajas
        # (Fase 44), para imprimir el "ingrese en…" al pie del presupuesto.
        # Vacío si la empresa no tiene ninguna marcada.
        "banco": (
            {
                "nombre": cuenta_banco.nombre,
                "entidad": cuenta_banco.banco or "",
                "iban": cuenta_banco.iban or "",
                "bic": cuenta_banco.bic or "",
            }
            if cuenta_banco
            else {}
        ),
    }


async def listar_plantillas(
    session: AsyncSession, cuenta_id: uuid.UUID
) -> list[PlantillaPresupuesto]:
    filas = await session.execute(
        select(PlantillaPresupuesto)
        .where(
            PlantillaPresupuesto.activo.is_(True),
            (PlantillaPresupuesto.cuenta_id == cuenta_id) | (PlantillaPresupuesto.cuenta_id.is_(None)),
        )
        .order_by(PlantillaPresupuesto.es_sistema.desc(), PlantillaPresupuesto.nombre)
    )
    return list(filas.scalars())


async def obtener_plantilla(
    session: AsyncSession, plantilla_id: uuid.UUID, cuenta_id: uuid.UUID
) -> PlantillaPresupuesto | None:
    """Una plantilla visible para la cuenta: la suya propia o una de sistema."""
    plantilla = await session.get(PlantillaPresupuesto, plantilla_id)
    if plantilla is None or not plantilla.activo:
        return None
    if plantilla.cuenta_id is not None and plantilla.cuenta_id != cuenta_id:
        return None
    return plantilla


def _texto_de(elemento) -> str:
    return "".join(t.text or "" for t in elemento.iter(qn("w:t")))


def _detectar_tags_mal_separados(contenido: bytes) -> list[str]:
    """`docxtpl` exige que las etiquetas de fila (`{%tr for%}`/`{%tr endfor%}`,
    también `if`/`endif`) y de párrafo (`{%p if%}`/`{%p endif%}`, también
    `for`/`endfor`) vivan CADA UNA en su propia fila/párrafo — la fila o
    párrafo que contiene la etiqueta se sustituye entera por ella, así que si
    comparte fila/párrafo con más contenido (lo normal si se escriben juntas
    en Word), ese contenido desaparece y la etiqueta pareja queda huérfana:
    es la causa de "Encountered unknown tag 'endfor'/'endif'" en la enorme
    mayoría de los casos, y no un problema del propio fichero .docx.

    Se comprueba directamente sobre el XML, sin pasar por Jinja, para poder
    dar un mensaje específico en vez del genérico de sintaxis."""
    try:
        with ZipFile(BytesIO(contenido)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
    except (BadZipFile, KeyError):
        return []  # no es zip, o no es un docx con cuerpo — lo verá _validar_docx

    root = etree.fromstring(xml.encode("utf-8"))
    problemas = []

    for tr in root.iter(qn("w:tr")):
        txt = _texto_de(tr)
        tiene_apertura = "{%tr for" in txt or "{%tr if" in txt
        tiene_cierre = "{%tr endfor" in txt or "{%tr endif" in txt
        if tiene_apertura and tiene_cierre:
            problemas.append(
                "una fila de una tabla tiene la etiqueta de apertura (%tr for/if) "
                "y la de cierre (%tr endfor/endif) juntas en la misma fila"
            )

    for p in root.iter(qn("w:p")):
        txt = _texto_de(p)
        tiene_apertura = "{%p for" in txt or "{%p if" in txt
        tiene_cierre = "{%p endfor" in txt or "{%p endif" in txt
        if tiene_apertura and tiene_cierre:
            problemas.append(
                "un párrafo tiene la etiqueta de apertura (%p for/if) y la de "
                "cierre (%p endfor/endif) juntas en el mismo párrafo"
            )

    return problemas


def _validar_docx(contenido: bytes) -> set[str]:
    problemas_estructura = _detectar_tags_mal_separados(contenido)
    if problemas_estructura:
        detalle = "; ".join(problemas_estructura)
        raise PlantillaInvalida(
            mensaje_usuario=(
                "La plantilla tiene un bucle o una condición de tabla mal "
                "colocados: la etiqueta que abre el bucle/condición y la que "
                "lo cierra tienen que estar cada una en su propia fila (o "
                "párrafo), no juntas con los datos. Puedes repararla tú "
                "moviendo la etiqueta de cierre a una fila o párrafo nuevo, "
                "o dejar que la aplicación lo intente arreglar sola."
            ),
            nota_tecnica=(
                "docxtpl sustituye la fila/párrafo que contiene una etiqueta "
                "{%tr/%p ...%} por esa etiqueta sola, descartando el resto de "
                "su contenido; si apertura y cierre comparten fila/párrafo, la "
                "primera 'engulle' a la segunda y Jinja acaba viendo un "
                "endfor/endif sin for/if — de ahí el error de sintaxis "
                "genérico que se veía antes. Detectado: " + detalle
            ),
            reparable=True,
        )

    try:
        return DocxTemplate(BytesIO(contenido)).get_undeclared_template_variables(
            jinja_env=_entorno_jinja()
        )
    except (BadZipFile, PackageNotFoundError) as exc:
        # El fichero no se puede abrir como paquete OOXML: no es un .docx real
        # (texto plano, un .doc antiguo renombrado, un fichero corrupto...).
        raise PlantillaInvalida(
            mensaje_usuario=(
                "El archivo no se puede abrir como documento Word: no es un "
                ".docx válido. Ábrelo en Word y guárdalo de nuevo como "
                "'Documento de Word (.docx)' antes de subirlo."
            ),
            nota_tecnica=f"{type(exc).__name__}: {exc}",
        ) from exc
    except TemplateSyntaxError as exc:
        # El .docx en sí es válido, pero sus marcadores {{ }} tienen un error
        # de sintaxis Jinja — casi siempre porque Word autocorrige las llaves.
        raise PlantillaInvalida(
            mensaje_usuario=(
                "El documento es un .docx válido, pero tiene un error de "
                "sintaxis en uno de sus marcadores. Esto suele pasar porque "
                "Word autocorrige las llaves dobles al escribirlas: prueba a "
                "desactivar el autocorrector (Archivo → Opciones → Revisión → "
                "Autocorrección) o a pegar los marcadores sin formato "
                "(Ctrl+Shift+V) y vuelve a subir el archivo."
            ),
            nota_tecnica=(
                f"jinja2.TemplateSyntaxError en línea {exc.lineno}: {exc.message}"
                if exc.lineno
                else f"jinja2.TemplateSyntaxError: {exc.message}"
            ),
        ) from exc
    except Exception as exc:  # cualquier otro fallo de lectura de docxtpl/python-docx
        raise PlantillaInvalida(
            mensaje_usuario=(
                "No se ha podido leer la plantilla. Revisa que el archivo no esté dañado."
            ),
            nota_tecnica=f"{type(exc).__name__}: {exc}",
        ) from exc


def reparar_tags_docxtpl(contenido: bytes) -> bytes:
    """Arregla el caso detectado por `_detectar_tags_mal_separados`: separa
    la etiqueta de apertura y la de cierre de un bucle/condición de tabla o
    párrafo, cada una a su propia fila/párrafo, sin tocar nada más.

    Es una reparación mecánica y determinista (no pasa por ningún modelo de
    IA) — es la fila/párrafo exacto el que hay que mover, no algo que haya
    que adivinar, así que un arreglo mecánico es más fiable y no gasta
    tokens de IA. Verificado con render real antes de usarse en producción:
    ver la conversación de la incidencia."""
    doc = Document(BytesIO(contenido))

    for tabla in doc.tables:
        for fila in list(tabla.rows):
            tr = fila._tr
            txt = _texto_de(tr)
            tiene_apertura = "{%tr for" in txt or "{%tr if" in txt
            tiene_cierre = "{%tr endfor" in txt or "{%tr endif" in txt
            if not (tiene_apertura and tiene_cierre):
                continue

            apertura_txt = None
            for prefijo in ("{%tr for ", "{%tr if "):
                for t in tr.iter(qn("w:t")):
                    if t.text and prefijo in t.text:
                        ini = t.text.index(prefijo)
                        fin = t.text.index("%}", ini) + 2
                        apertura_txt = t.text[ini:fin]
                        t.text = t.text[:ini] + t.text[fin:]
                        break
                if apertura_txt is not None:
                    break

            cierre_txt = None
            for marca in ("{%tr endfor %}", "{%tr endif %}"):
                for t in tr.iter(qn("w:t")):
                    if t.text and marca in t.text:
                        t.text = t.text.replace(marca, "")
                        cierre_txt = marca
                        break
                if cierre_txt is not None:
                    break

            if apertura_txt is None or cierre_txt is None:
                continue

            fila_apertura = copy.deepcopy(tr)
            primero = True
            for t in fila_apertura.iter(qn("w:t")):
                t.text = apertura_txt if primero else ""
                primero = False

            fila_cierre = copy.deepcopy(tr)
            primero = True
            for t in fila_cierre.iter(qn("w:t")):
                t.text = cierre_txt if primero else ""
                primero = False

            tr.addprevious(fila_apertura)
            tr.addnext(fila_cierre)

    body = doc.element.body
    for p in list(body.iter(qn("w:p"))):
        txt = _texto_de(p)
        tiene_apertura = "{%p for" in txt or "{%p if" in txt
        tiene_cierre = "{%p endfor" in txt or "{%p endif" in txt
        if not (tiene_apertura and tiene_cierre):
            continue

        for prefijo in ("{%p if ", "{%p for "):
            ini = txt.find(prefijo)
            if ini == -1:
                continue
            fin = txt.index("%}", ini) + 2
            _aislar_etiqueta_en_parrafo_propio(p, txt[ini:fin], antes=True)
            break

        for marca in ("{%p endif %}", "{%p endfor %}"):
            if marca in _texto_de(p):
                _aislar_etiqueta_en_parrafo_propio(p, marca, antes=False)
                break

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _aislar_etiqueta_en_parrafo_propio(p, marca: str, antes: bool) -> bool:
    """Saca `marca` (una etiqueta {%p ...%}) de `p` a un párrafo nuevo ella
    sola, insertado antes o después de `p`. `marca` puede compartir el mismo
    <w:r> con más texto, separada por <w:br/> (líneas con Mayús+Intro)."""
    for t in p.iter(qn("w:t")):
        if not t.text or marca not in t.text:
            continue
        resto_antes, resto_despues = t.text.split(marca, 1)
        run = t.getparent()
        hijos = list(run)
        idx = hijos.index(t)
        quitar_br_prev = idx > 0 and hijos[idx - 1].tag == qn("w:br")
        quitar_br_next = idx + 1 < len(hijos) and hijos[idx + 1].tag == qn("w:br")

        nuevo_p = copy.deepcopy(p)
        for h in list(nuevo_p):
            if h.tag != qn("w:pPr"):
                nuevo_p.remove(h)
        nuevo_run = copy.deepcopy(run)
        for h in list(nuevo_run):
            nuevo_run.remove(h)
        nuevo_t = copy.deepcopy(t)
        nuevo_t.text = marca
        nuevo_run.append(nuevo_t)
        nuevo_p.append(nuevo_run)

        t.text = resto_antes + resto_despues
        if quitar_br_prev:
            run.remove(hijos[idx - 1])
        if quitar_br_next and hijos[idx + 1] in run:
            run.remove(hijos[idx + 1])
        if t.text == "" and len(list(run.iter(qn("w:t")))) > 1:
            run.remove(t)

        if antes:
            p.addprevious(nuevo_p)
        else:
            p.addnext(nuevo_p)
        return True
    return False


async def subir_plantilla(
    session: AsyncSession, cuenta_id: uuid.UUID, nombre: str, contenido: bytes
) -> PlantillaPresupuesto:
    claves = sorted(_validar_docx(contenido))
    object_key = f"plantillas-presupuesto/{cuenta_id}/{uuid.uuid4()}.docx"
    await storage.subir_objeto(
        object_key, contenido, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    plantilla = PlantillaPresupuesto(
        cuenta_id=cuenta_id,
        es_sistema=False,
        nombre=nombre,
        archivo_docx_key=object_key,
        claves_detectadas=claves,
        **datos_autoria(),
    )
    session.add(plantilla)
    await session.flush()
    return plantilla


async def eliminar_plantilla(session: AsyncSession, cuenta_id: uuid.UUID, plantilla_id: uuid.UUID) -> bool:
    plantilla = await session.get(PlantillaPresupuesto, plantilla_id)
    if plantilla is None or plantilla.es_sistema or plantilla.cuenta_id != cuenta_id:
        return False
    await storage.eliminar_objeto(plantilla.archivo_docx_key)
    await session.delete(plantilla)
    await session.flush()
    return True


async def generar_documento(
    session: AsyncSession,
    presupuesto: Presupuesto,
    plantilla: PlantillaPresupuesto,
    formato: str,
) -> bytes:
    archivo = await storage.descargar_objeto(plantilla.archivo_docx_key)
    doc = DocxTemplate(BytesIO(archivo))
    contexto = await contexto_plantilla(session, presupuesto)
    doc.render(contexto, jinja_env=_entorno_jinja())

    # El logo no es una clave `{{ }}`: es una imagen ya insertada en el Word
    # cuyo texto alternativo (clic derecho → Editar texto alternativo) sea
    # exactamente "logo" — `replace_pic` la localiza por ese texto y sustituye
    # sus bytes. Si la plantilla no tiene ninguna imagen así, no hace nada (no
    # todas las plantillas necesitan logo); si la organización no tiene logo
    # subido, se queda la imagen que trajera la plantilla.
    logo = await core_service.logo_de_organizacion(session, presupuesto.organization_id)
    if logo is not None:
        contenido_logo, _ = logo
        doc.replace_pic("logo", BytesIO(contenido_logo))

    salida = BytesIO()
    try:
        doc.save(salida)
    except ValueError:
        # La plantilla no tenía ninguna imagen con texto alternativo "logo"
        # que sustituir — no pasa nada, se guarda tal cual sin logo.
        doc.reset_replacements()
        salida = BytesIO()
        doc.save(salida)
    docx_bytes = salida.getvalue()

    if formato == "docx":
        return docx_bytes
    return await convertir_a_pdf_libreoffice(docx_bytes)


async def convertir_a_pdf_libreoffice(docx_bytes: bytes) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory() as directorio:
        ruta_docx = Path(directorio) / "documento.docx"
        ruta_docx.write_bytes(docx_bytes)
        perfil = Path(directorio) / "perfil"

        proceso = await asyncio.create_subprocess_exec(
            "soffice",
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{perfil}",
            "--convert-to",
            "pdf",
            "--outdir",
            directorio,
            str(ruta_docx),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            salida, error = await asyncio.wait_for(
                proceso.communicate(), timeout=TIMEOUT_CONVERSION_SEGUNDOS
            )
        except TimeoutError as exc:
            proceso.kill()
            raise ConversionPdfFallida("La conversión a PDF ha tardado demasiado") from exc

        ruta_pdf = Path(directorio) / "documento.pdf"
        if proceso.returncode != 0 or not ruta_pdf.exists():
            logger.error("Fallo de LibreOffice al convertir a PDF: %s", error.decode(errors="replace"))
            raise ConversionPdfFallida("No se ha podido generar el PDF de la plantilla")
        return ruta_pdf.read_bytes()


async def asegurar_plantillas_sistema() -> None:
    """Sube las 3 plantillas de sistema a MinIO y crea sus filas si faltan.
    Idempotente — se llama en cada arranque del API, sin bloquearlo si falla
    (mismo criterio que `storage.asegurar_bucket`)."""
    from app.core.database import SessionFactory

    async with SessionFactory() as session:
        for nombre, fichero, object_key in PLANTILLAS_SISTEMA:
            existente = await session.scalar(
                select(PlantillaPresupuesto).where(
                    PlantillaPresupuesto.es_sistema.is_(True),
                    PlantillaPresupuesto.archivo_docx_key == object_key,
                )
            )
            if existente is not None:
                continue
            ruta = DIRECTORIO_SISTEMA / fichero
            if not ruta.exists():
                logger.warning("Plantilla de sistema no encontrada en el repo: %s", ruta)
                continue
            contenido = ruta.read_bytes()
            claves = sorted(_validar_docx(contenido))
            await storage.subir_objeto(
                object_key,
                contenido,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            session.add(
                PlantillaPresupuesto(
                    cuenta_id=None,
                    es_sistema=True,
                    nombre=nombre,
                    archivo_docx_key=object_key,
                    claves_detectadas=claves,
                    creado_por_subject="sistema",
                    creado_por_nombre="Sistema",
                )
            )
        await session.commit()
