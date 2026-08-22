"""Plantillas Word: subir, listar, borrar, y rellenar con los datos de un
presupuesto para descargar en Word o PDF.

`docxtpl` (Jinja2 sobre `python-docx`) es el motor de relleno — las mismas
claves `{{ }}` que ya usa el resto de la app para HTML, pero dentro de un
`.docx` en vez de una plantilla en el repo. La conversión a PDF pasa por
LibreOffice en modo headless (Fase 39): no hay librería Python que convierta
DOCX→PDF con fidelidad, así que se invoca `soffice` como subproceso.
"""

import asyncio
import logging
import uuid
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate
from jinja2 import Environment
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
    pass


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
        "componentes_descompuesto": [
            {
                "concepto_codigo": c.codigo,
                "concepto_resumen": c.resumen,
                "hijo_codigo": linea.hijo.codigo if linea.hijo else "",
                "hijo_resumen": linea.hijo.resumen if linea.hijo else "",
                "hijo_unidad": linea.hijo.unidad if linea.hijo else "",
                "rendimiento": linea.rendimiento,
                "factor": linea.factor,
                "precio": linea.precio,
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


def _validar_docx(contenido: bytes) -> set[str]:
    try:
        return DocxTemplate(BytesIO(contenido)).get_undeclared_template_variables(
            jinja_env=_entorno_jinja()
        )
    except Exception as exc:  # cualquier fallo de lectura de docxtpl/python-docx
        raise PlantillaInvalida("El archivo no es un .docx válido") from exc


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
