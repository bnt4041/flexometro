"""Biblioteca de planos: alta, calibración y lo que se dibuja encima."""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.planos import dxf as lector_dxf
from app.modules.planos import geometria
from app.modules.planos import ia as lector_ia
from app.modules.planos.enums import TIPOS_QUE_MIDEN, UNIDAD_DE, OrigenPlano, TipoElemento
from app.modules.planos.models import CapaPlano, ElementoPlano, HojaPlano, Plano

logger = logging.getLogger(__name__)

MAX_TAMANO_BYTES = 40 * 1024 * 1024
MIME_PERMITIDOS = {
    "application/pdf": OrigenPlano.PDF,
    "image/png": OrigenPlano.IMAGEN,
    "image/jpeg": OrigenPlano.IMAGEN,
    "image/webp": OrigenPlano.IMAGEN,
}

#: Un DXF llega con el tipo que le ponga el navegador, y no hay ninguno
#: acordado: unos mandan `image/vnd.dxf`, otros `application/dxf` y muchos
#: `application/octet-stream`. Se decide por la extensión, que es lo único
#: fiable aquí.
EXTENSIONES_DXF = (".dxf",)

#: Doce colores para repartir entre las capas del DXF. El fichero trae sus
#: propios colores, pero son índices de la paleta de AutoCAD sobre fondo
#: negro: en pantalla blanca la mitad no se ven.
COLORES_CAPA = (
    "#b45309", "#1d4ed8", "#15803d", "#b91c1c", "#7c3aed", "#0e7490",
    "#a16207", "#be185d", "#4d7c0f", "#c2410c", "#4338ca", "#0f766e",
)
#: Un PDF de obra puede traer muchas láminas, pero mil hojas es un fichero
#: equivocado, no una entrega.
MAX_HOJAS = 200


class PlanoInvalido(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    return await siguiente_referencia_libre(
        session,
        organization_id=require_organization_id(),
        tipo_documento="plano",
        existe=lambda c: _existe_codigo(session, c),
    )


async def _existe_codigo(session: AsyncSession, codigo: str) -> bool:
    return bool(
        await session.scalar(
            select(Plano.id).where(
                Plano.organization_id == require_organization_id(), Plano.codigo == codigo
            )
        )
    )


async def crear_plano(
    session: AsyncSession,
    *,
    nombre: str,
    descripcion: str | None,
    obra_id: uuid.UUID | None,
    presupuesto_id: uuid.UUID | None,
    nombre_archivo: str,
    content_type: str,
    contenido: bytes,
    hojas: list[dict],
) -> Plano:
    """Da de alta el plano y sus hojas.

    Las dimensiones de cada hoja las manda el navegador, que es quien abre el
    PDF con pdf.js y sabe cuánto mide cada página. Fiarse de él no abre
    ninguna puerta: esas dimensiones solo definen el sistema de coordenadas en
    el que se dibuja, y la escala real se fija después calibrando DENTRO de ese
    mismo sistema. Una página declarada con el doble de tamaño da exactamente
    las mismas mediciones. La alternativa —rasterizar en el servidor— traería
    una librería de PDF y bastante memoria a cambio de nada.
    """
    es_dxf = nombre_archivo.lower().endswith(EXTENSIONES_DXF)
    origen = OrigenPlano.DXF if es_dxf else MIME_PERMITIDOS.get(content_type)
    if origen is None:
        raise PlanoInvalido(f"Formato no admitido: {content_type}")
    if not contenido:
        raise PlanoInvalido("El fichero está vacío")
    if len(contenido) > MAX_TAMANO_BYTES:
        raise PlanoInvalido(
            f"El fichero pasa de {MAX_TAMANO_BYTES // (1024 * 1024)} MB"
        )

    # En un DXF las hojas NO las manda el navegador: la geometría se lee aquí,
    # y de ella salen las dimensiones, las capas y hasta la escala. Aceptar lo
    # que dijera el cliente sería descartar el dato bueno por el de oídas.
    dibujo = lector_dxf.leer(contenido) if es_dxf else None
    if dibujo is not None:
        hojas = [{"ancho": dibujo.ancho, "alto": dibujo.alto}]

    if not hojas:
        raise PlanoInvalido("No se ha podido leer ninguna página del fichero")
    if len(hojas) > MAX_HOJAS:
        raise PlanoInvalido(f"Demasiadas páginas (máximo {MAX_HOJAS})")

    org_id = require_organization_id()
    object_key = f"{org_id}/planos/{uuid.uuid4()}-{nombre_archivo}"
    await storage.subir_objeto(object_key, contenido, content_type)

    plano = Plano(
        organization_id=org_id,
        codigo=await siguiente_codigo(session),
        nombre=nombre,
        descripcion=descripcion,
        obra_id=obra_id,
        presupuesto_id=presupuesto_id,
        origen=origen,
        object_key=object_key,
        nombre_archivo=nombre_archivo,
        content_type=content_type,
        tamano_bytes=len(contenido),
        **datos_autoria(),
    )
    session.add(plano)
    await session.flush()

    for indice, hoja in enumerate(hojas, start=1):
        ancho = Decimal(str(hoja.get("ancho") or 0))
        alto = Decimal(str(hoja.get("alto") or 0))
        if ancho <= 0 or alto <= 0:
            raise PlanoInvalido(f"La página {indice} no tiene dimensiones válidas")
        session.add(
            HojaPlano(
                organization_id=org_id,
                plano_id=plano.id,
                numero=indice,
                nombre=hoja.get("nombre"),
                ancho=ancho,
                alto=alto,
                dibujo=lector_dxf.a_json(dibujo) if dibujo is not None else None,
                # Un DXF suele declarar sus unidades, así que nace calibrado y
                # se puede medir desde el primer momento. Es la diferencia de
                # verdad frente a un plano escaneado.
                metros_por_unidad=dibujo.metros_por_unidad if dibujo else None,
            )
        )

    if dibujo is not None and dibujo.capas:
        # Las capas del fichero, tal cual: son las que ha usado quien dibujó el
        # plano, y renombrarlas o agruparlas aquí sería perder su criterio.
        for orden, nombre_capa in enumerate(dibujo.capas):
            session.add(
                CapaPlano(
                    organization_id=org_id,
                    plano_id=plano.id,
                    nombre=nombre_capa[:120],
                    color=COLORES_CAPA[orden % len(COLORES_CAPA)],
                    orden=orden,
                )
            )
    else:
        # Una capa para empezar: dibujar no debería obligar a crear capas antes
        # de haber dibujado nada, y sin ninguna la pantalla de capas sale vacía
        # y parece rota.
        session.add(
            CapaPlano(
                organization_id=org_id, plano_id=plano.id, nombre="General", orden=0
            )
        )
    await session.flush()
    await session.refresh(plano, ["hojas", "capas"])
    return plano


async def obtener_plano(session: AsyncSession, plano_id: uuid.UUID) -> Plano | None:
    return await session.scalar(
        select(Plano).where(
            Plano.id == plano_id, Plano.organization_id == require_organization_id()
        )
    )


async def obtener_hoja(session: AsyncSession, hoja_id: uuid.UUID) -> HojaPlano | None:
    return await session.scalar(
        select(HojaPlano).where(
            HojaPlano.id == hoja_id,
            HojaPlano.organization_id == require_organization_id(),
        )
    )


async def borrar_plano(session: AsyncSession, plano: Plano) -> None:
    clave = plano.object_key
    await session.delete(plano)
    await session.flush()
    try:
        await storage.eliminar_objeto(clave)
    except Exception:  # noqa: BLE001
        # El fichero huérfano en el almacén es un problema de limpieza; hacer
        # fallar el borrado por eso dejaría el plano visible y sin poder
        # quitarlo, que es peor.
        logger.warning("No se pudo borrar %s del almacén", clave, exc_info=True)


# ── Calibración ─────────────────────────────────────────────────────────


async def calibrar(
    session: AsyncSession, hoja: HojaPlano, *, a: dict, b: dict, distancia_m: Decimal
) -> HojaPlano:
    """Fija la escala de la hoja y **vuelve a calcular lo ya medido**.

    Lo segundo es lo importante. Recalibrar suele pasar justo porque la escala
    estaba mal, y dejar las mediciones viejas con el número antiguo produciría
    una hoja donde unas cifras son de una escala y otras de otra, sin nada que
    lo indique.
    """
    hoja.metros_por_unidad = geometria.escala_desde_cota(a, b, distancia_m)
    hoja.calibracion = {"a": a, "b": b, "distancia_m": str(distancia_m)}
    await session.flush()
    await recalcular_hoja(session, hoja)
    return hoja


async def calibrar_por_escala_impresa(
    session: AsyncSession, hoja: HojaPlano, plano: Plano, denominador: int
) -> HojaPlano:
    """Calibra con la escala escrita en el plano, sin estimar nada.

    Solo vale para PDF, y no es un capricho: las coordenadas de un PDF son
    puntos, que son una medida de papel, y de ahí sale la cuenta exacta. Las de
    una imagen son píxeles, y un píxel no mide nada sin saber a qué resolución
    se escaneó — un JPG a 150 o a 600 ppp se ve igual y daría escalas que
    difieren por cuatro.
    """
    if plano.origen != OrigenPlano.PDF:
        raise PlanoInvalido(
            "La escala impresa solo se puede aplicar a un PDF: en una imagen un "
            "píxel no mide nada sin saber a qué resolución se escaneó. Calíbrala "
            "pinchando una cota."
        )
    hoja.metros_por_unidad = lector_ia.escala_de_papel(denominador)
    hoja.calibracion = {"escala_impresa": denominador}
    await session.flush()
    await recalcular_hoja(session, hoja)
    return hoja


async def recalcular_hoja(session: AsyncSession, hoja: HojaPlano) -> int:
    elementos = list(
        await session.scalars(
            select(ElementoPlano).where(ElementoPlano.hoja_id == hoja.id)
        )
    )
    tocados = 0
    for elemento in elementos:
        if elemento.tipo not in TIPOS_QUE_MIDEN:
            continue
        try:
            elemento.valor, elemento.unidad = _medir(elemento.tipo, elemento.geometria, hoja)
        except geometria.GeometriaInvalida:
            elemento.valor, elemento.unidad = None, None
        tocados += 1
    await session.flush()
    return tocados


def _medir(
    tipo: TipoElemento, forma: list, hoja: HojaPlano
) -> tuple[Decimal | None, str | None]:
    """El número de un elemento, o nada si todavía no se puede saber.

    Sin escala no se mide. Devolver un número «en unidades de hoja» sería peor
    que no devolver nada: se leería como metros.
    """
    if tipo not in TIPOS_QUE_MIDEN:
        return None, None
    if tipo == TipoElemento.CONTEO:
        return geometria.conteo(forma), UNIDAD_DE[tipo]
    if hoja.metros_por_unidad is None:
        return None, None
    escala = Decimal(str(hoja.metros_por_unidad))
    if tipo == TipoElemento.LONGITUD:
        return geometria.longitud(forma, escala), UNIDAD_DE[tipo]
    return geometria.area(forma, escala), UNIDAD_DE[tipo]


# ── Elementos ───────────────────────────────────────────────────────────


async def guardar_elemento(
    session: AsyncSession,
    hoja: HojaPlano,
    *,
    tipo: TipoElemento,
    forma: list,
    capa_id: uuid.UUID | None,
    texto: str | None,
    color: str | None,
    elemento: ElementoPlano | None = None,
) -> ElementoPlano:
    valor, unidad = _medir(tipo, forma, hoja)
    if elemento is None:
        elemento = ElementoPlano(
            organization_id=require_organization_id(),
            hoja_id=hoja.id,
            **datos_autoria(),
        )
        session.add(elemento)
    elemento.tipo = tipo
    elemento.geometria = forma
    elemento.capa_id = capa_id
    elemento.texto = texto
    elemento.color = color
    elemento.valor = valor
    elemento.unidad = unidad
    await session.flush()
    return elemento


async def obtener_elemento(
    session: AsyncSession, elemento_id: uuid.UUID
) -> ElementoPlano | None:
    return await session.scalar(
        select(ElementoPlano).where(
            ElementoPlano.id == elemento_id,
            ElementoPlano.organization_id == require_organization_id(),
        )
    )


async def elementos_de(session: AsyncSession, hoja_id: uuid.UUID) -> list[ElementoPlano]:
    return list(
        await session.scalars(
            select(ElementoPlano)
            .where(
                ElementoPlano.hoja_id == hoja_id,
                ElementoPlano.organization_id == require_organization_id(),
            )
            .order_by(ElementoPlano.created_at)
        )
    )


# ── Llevar una medición a una partida ───────────────────────────────────


class MedicionNoAplicable(Exception):
    pass


async def aplicar_a_partida(
    session: AsyncSession, elemento: ElementoPlano, partida_id: uuid.UUID
) -> uuid.UUID:
    """Escribe la medición como una línea de la partida.

    Pasa por `crear_linea`, igual que si se hubiese tecleado a mano, para que
    el recálculo de la partida y del presupuesto sea exactamente el mismo. Y
    se comprueba que la unidad de la partida es la que produce este tipo de
    medición: meter metros cuadrados en una partida de metros lineales da un
    presupuesto que cuadra por dentro y está mal por fuera.
    """
    from app.modules.presupuestos.presupuesto_schemas import LineaMedicionCreate
    from app.modules.presupuestos.presupuesto_service import crear_linea, obtener_partida

    if elemento.tipo not in TIPOS_QUE_MIDEN:
        raise MedicionNoAplicable("Eso no es una medición")
    if elemento.valor is None:
        raise MedicionNoAplicable("La hoja todavía no está calibrada")
    if elemento.linea_medicion_id is not None:
        raise MedicionNoAplicable("Esta medición ya se llevó a una partida")

    partida = await obtener_partida(session, partida_id)
    if partida is None:
        raise MedicionNoAplicable("La partida no existe")

    esperada = UNIDAD_DE[elemento.tipo]
    if _normalizar_unidad(partida.unidad) != esperada:
        raise MedicionNoAplicable(
            f"La partida está en «{partida.unidad}» y esto mide en «{esperada}»"
        )

    hoja = await session.get(HojaPlano, elemento.hoja_id)
    plano = await session.get(Plano, hoja.plano_id) if hoja else None
    procedencia = f"{plano.codigo} hoja {hoja.numero}" if plano and hoja else "plano"
    comentario = f"{elemento.texto or 'Medido sobre plano'} ({procedencia})"

    if elemento.tipo == TipoElemento.CONTEO:
        datos = LineaMedicionCreate(comentario=comentario[:250], uds=elemento.valor)
    else:
        datos = LineaMedicionCreate(
            comentario=comentario[:250], uds=Decimal(1), longitud=elemento.valor
        )

    linea = await crear_linea(session, partida_id, datos)
    if linea is None:
        raise MedicionNoAplicable("No se ha podido crear la línea")
    elemento.linea_medicion_id = linea.id
    await session.flush()
    return linea.id


def _normalizar_unidad(unidad: str | None) -> str:
    """«m²», «M2» y «m2» son lo mismo escrito de tres maneras, y en un banco de
    precios real aparecen las tres."""
    return (unidad or "").strip().lower().replace("²", "2").replace("³", "3")
