"""Importación de un BC3 a la base de datos.

El cálculo de precios se hace **en memoria**, en orden topológico, antes de
escribir nada. Un banco como BEDEC trae decenas de miles de conceptos, y hacerlo
con la cascada por SQL supondría una consulta por nodo: minutos en vez de
segundos. El resultado es el mismo porque se aplican las mismas reglas de
redondeo.

Eso además regala una validación valiosa: el fichero trae sus propios precios, y
comparar los nuestros con los suyos dice si nuestro modelo de redondeo coincide
con el del programa que lo generó.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import OrigenDato
from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.presupuestos.fiebdc.modelo import (
    ArchivoBC3,
    ConceptoBC3,
    TipoConceptoBC3,
)
from app.modules.presupuestos.models import (
    Concepto,
    Descomposicion,
    NaturalezaConcepto,
    OrigenPrecio,
    TipoConcepto,
)
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    LineaMedicion,
    Partida,
    Presupuesto,
)
from app.modules.presupuestos.presupuesto_calculo import parcial_de

# Los conceptos que el árbol de precios reconoce; capítulos y raíz son
# estructura del presupuesto, no precios.
TIPOS_PRECIO = {
    TipoConceptoBC3.BASICO: TipoConcepto.BASICO,
    TipoConceptoBC3.AUXILIAR: TipoConcepto.AUXILIAR,
    TipoConceptoBC3.UNITARIO: TipoConcepto.UNITARIO,
}


class EstrategiaCodigos(StrEnum):
    OMITIR = "omitir"        # respeta lo que ya hay
    ACTUALIZAR = "actualizar"  # pisa precio y descripción con los del fichero


@dataclass
class ResultadoImportacion:
    conceptos_creados: int = 0
    conceptos_omitidos: int = 0
    conceptos_actualizados: int = 0
    lineas_descomposicion: int = 0
    presupuesto_id: uuid.UUID | None = None
    capitulos: int = 0
    partidas: int = 0
    lineas_medicion: int = 0
    # Conceptos cuyo precio recalculado no coincide con el del fichero.
    discrepancias: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)
    ciclos: list[str] = field(default_factory=list)
    incidencias: list[str] = field(default_factory=list)

    @property
    def discrepancia_maxima(self) -> Decimal:
        if not self.discrepancias:
            return Decimal("0.00")
        return max(abs(nuestro - suyo) for _, nuestro, suyo in self.discrepancias)


def detectar_ciclos(archivo: ArchivoBC3) -> list[str]:
    """Ciclos en la descomposición, buscados en memoria.

    Un BC3 correcto no los tiene, pero un fichero corrupto sí puede, y meterlo
    en base de datos dejaría el recálculo dando vueltas.
    """
    estado: dict[str, int] = {}  # 0 sin visitar, 1 en curso, 2 cerrado
    ciclos: list[str] = []

    def visitar(codigo: str, camino: list[str]) -> None:
        if estado.get(codigo, 0) == 2:
            return
        if estado.get(codigo, 0) == 1:
            inicio = camino.index(codigo) if codigo in camino else 0
            ciclos.append(" -> ".join([*camino[inicio:], codigo]))
            return
        estado[codigo] = 1
        for linea in archivo.descomposiciones.get(codigo, []):
            visitar(linea.hijo, [*camino, codigo])
        estado[codigo] = 2

    for codigo in list(archivo.descomposiciones):
        visitar(codigo, [])
    return ciclos


def orden_topologico(archivo: ArchivoBC3) -> list[str]:
    """Códigos ordenados de hijos a padres, para poder calcular de abajo arriba."""
    visitado: set[str] = set()
    orden: list[str] = []

    def visitar(codigo: str, profundidad: int = 0) -> None:
        if codigo in visitado or profundidad > 60:
            return
        visitado.add(codigo)
        for linea in archivo.descomposiciones.get(codigo, []):
            visitar(linea.hijo, profundidad + 1)
        orden.append(codigo)

    for codigo in archivo.conceptos:
        visitar(codigo)
    return orden


def calcular_precios(archivo: ArchivoBC3) -> tuple[dict[str, Decimal], list]:
    """Precio de cada concepto según nuestras reglas, y dónde discrepa del fichero.

    Los básicos toman el precio del fichero. Los descompuestos se calculan
    sumando líneas ya redondeadas a dos decimales, que es la convención Presto
    que aplicamos en todo el sistema.
    """
    precios: dict[str, Decimal] = {}
    discrepancias = []

    for codigo in orden_topologico(archivo):
        concepto = archivo.conceptos.get(codigo)
        lineas = archivo.descomposiciones.get(codigo)

        if not lineas:
            precios[codigo] = redondear_precio(
                concepto.precio if concepto else Decimal("0")
            )
            continue

        total = Decimal("0.00")
        for linea in lineas:
            total += redondear_precio(
                linea.rendimiento * linea.factor * precios.get(linea.hijo, Decimal("0"))
            )
        calculado = redondear_precio(total)
        precios[codigo] = calculado

        if concepto is not None and concepto.precio:
            declarado = redondear_precio(concepto.precio)
            if declarado != calculado:
                discrepancias.append((codigo, calculado, declarado))

    return precios, discrepancias


async def _importar_conceptos(
    session: AsyncSession,
    archivo: ArchivoBC3,
    precios: dict[str, Decimal],
    estrategia: EstrategiaCodigos,
    resultado: ResultadoImportacion,
) -> dict[str, uuid.UUID]:
    """Sube al catálogo de precios los conceptos básicos/auxiliares/unitarios
    del fichero. Independiente de si el fichero acaba formando un presupuesto
    nuevo, insertándose bajo un capítulo existente, o ninguna de las dos —
    por eso vive separado de `_importar_presupuesto`/`_recorrer_bc3`."""
    org_id = require_organization_id()
    existentes = dict(
        (
            await session.execute(
                select(Concepto.codigo, Concepto.id).where(
                    Concepto.organization_id == org_id
                )
            )
        ).all()
    )

    a_crear: list[dict] = []
    para_precio = {c for c, x in archivo.conceptos.items() if x.tipo in TIPOS_PRECIO}

    for codigo in sorted(para_precio):
        concepto = archivo.conceptos[codigo]
        if codigo in existentes:
            if estrategia is EstrategiaCodigos.OMITIR:
                resultado.conceptos_omitidos += 1
                continue
            await session.execute(
                Concepto.__table__.update()
                .where(Concepto.id == existentes[codigo])
                .values(
                    resumen=concepto.resumen or codigo,
                    unidad=concepto.unidad or "ud",
                    precio=precios.get(codigo, Decimal("0.00")),
                    texto=concepto.texto,
                    origen_dato=OrigenDato.FIEBDC3,
                )
            )
            resultado.conceptos_actualizados += 1
            continue

        nuevo_id = uuid.uuid4()
        existentes[codigo] = nuevo_id
        a_crear.append(_fila_concepto(org_id, nuevo_id, concepto, precios, archivo))

    if a_crear:
        # Inserción masiva: una sentencia en vez de una por concepto.
        await session.execute(insert(Concepto), a_crear)
        resultado.conceptos_creados = len(a_crear)

    # --- Descomposición ---

    lineas_desc: list[dict] = []
    for padre, lineas in archivo.descomposiciones.items():
        if padre not in para_precio or padre not in existentes:
            continue
        for orden, linea in enumerate(lineas):
            hijo_id = existentes.get(linea.hijo)
            if hijo_id is None:
                resultado.incidencias.append(
                    f"'{padre}' referencia a '{linea.hijo}', que no está en el fichero"
                )
                continue
            lineas_desc.append(
                {
                    "id": uuid.uuid4(),
                    "organization_id": org_id,
                    "padre_id": existentes[padre],
                    "hijo_id": hijo_id,
                    "rendimiento": linea.rendimiento,
                    "factor": linea.factor,
                    "orden": orden,
                }
            )

    if lineas_desc:
        await session.execute(insert(Descomposicion), lineas_desc)
        resultado.lineas_descomposicion = len(lineas_desc)

    await session.flush()
    return existentes


async def importar(
    session: AsyncSession,
    archivo: ArchivoBC3,
    *,
    estrategia: EstrategiaCodigos = EstrategiaCodigos.OMITIR,
    crear_presupuesto: bool = True,
    nombre_presupuesto: str | None = None,
    codigo_presupuesto: str | None = None,
    capitulo_banco_id: uuid.UUID | None = None,
) -> ResultadoImportacion:
    resultado = ResultadoImportacion(
        incidencias=[f"línea {i.linea} {i.registro}: {i.detalle}" for i in archivo.incidencias]
    )

    resultado.ciclos = detectar_ciclos(archivo)
    if resultado.ciclos:
        # Con ciclos no se escribe nada: el árbol de precios no sería calculable.
        return resultado

    precios, discrepancias = calcular_precios(archivo)
    resultado.discrepancias = discrepancias

    existentes = await _importar_conceptos(session, archivo, precios, estrategia, resultado)

    # Soltar un BC3 sobre un capítulo del banco (Fase 50): las fichas que
    # venían en el fichero se colocan ahí. Solo las de ESTE fichero, no las
    # que ya existían con otro código — `existentes` trae el mapa completo
    # de la organización, así que se cruza con los códigos del archivo.
    if capitulo_banco_id is not None:
        ids = [existentes[c] for c in archivo.conceptos if c in existentes]
        if ids:
            await session.execute(
                update(Concepto)
                .where(Concepto.id.in_(ids))
                .values(capitulo_id=capitulo_banco_id)
            )

    if crear_presupuesto and archivo.es_presupuesto:
        await _importar_presupuesto(
            session,
            archivo,
            existentes,
            precios,
            resultado,
            nombre_presupuesto=nombre_presupuesto,
            codigo_presupuesto=codigo_presupuesto,
        )

    return resultado


async def _parsear_y_subir_conceptos(
    session: AsyncSession,
    archivo: ArchivoBC3,
    estrategia: EstrategiaCodigos,
) -> tuple[ResultadoImportacion, dict[str, uuid.UUID], dict[str, Decimal]]:
    """Ciclos, precios y catálogo: la parte común a `importar_bajo_capitulo` y
    `importar_en_raiz` antes de decidir dónde colgar el árbol. Si hay ciclos,
    o el fichero no trae estructura de presupuesto, `existentes`/`precios`
    salen vacíos y el llamador debe devolver `resultado` tal cual — se
    reconoce por `resultado.ciclos` o `not archivo.es_presupuesto`."""
    resultado = ResultadoImportacion(
        incidencias=[f"línea {i.linea} {i.registro}: {i.detalle}" for i in archivo.incidencias]
    )

    resultado.ciclos = detectar_ciclos(archivo)
    if resultado.ciclos:
        return resultado, {}, {}

    precios, discrepancias = calcular_precios(archivo)
    resultado.discrepancias = discrepancias

    existentes = await _importar_conceptos(session, archivo, precios, estrategia, resultado)

    if not archivo.es_presupuesto or archivo.raiz is None:
        resultado.incidencias.append(
            "El fichero no trae una estructura de capítulos/partidas que insertar "
            "(solo conceptos de precio, ya subidos al catálogo)"
        )
        return resultado, existentes, precios

    return resultado, existentes, precios


async def importar_bajo_capitulo(
    session: AsyncSession,
    archivo: ArchivoBC3,
    capitulo_id: uuid.UUID,
    *,
    estrategia: EstrategiaCodigos = EstrategiaCodigos.OMITIR,
) -> ResultadoImportacion:
    """Igual que `importar`, pero en vez de crear un presupuesto nuevo cuelga
    la estructura del fichero (subcapítulos y partidas, con sus mediciones)
    de un capítulo que ya existe — arrastrar un BC3 sobre una fila del
    presupuesto, en vez de "Importar BC3" como pantalla aparte.

    El catálogo de precios se sube exactamente igual que en `importar`; lo
    único que cambia es el destino del árbol de capítulos/partidas.
    """
    org_id = require_organization_id()
    resultado, existentes, precios = await _parsear_y_subir_conceptos(session, archivo, estrategia)
    if resultado.ciclos or not archivo.es_presupuesto or archivo.raiz is None:
        return resultado

    capitulo = await session.scalar(
        select(Capitulo).where(Capitulo.id == capitulo_id, Capitulo.organization_id == org_id)
    )
    if capitulo is None:
        resultado.incidencias.append("El capítulo destino no existe")
        return resultado

    # Dos secuencias de orden independientes (capítulos y partidas no
    # comparten numeración dentro de un mismo padre — mismo criterio que
    # `siguienteOrden` en el frontend), para que lo nuevo se coloque detrás
    # de lo que ya hubiera, no se intercale ni empiece en 0.
    orden_cap = await session.scalar(
        select(func.max(Capitulo.orden)).where(Capitulo.parent_id == capitulo_id)
    )
    orden_part = await session.scalar(
        select(func.max(Partida.orden)).where(Partida.capitulo_id == capitulo_id)
    )

    resultado.presupuesto_id = capitulo.presupuesto_id
    await _recorrer_bc3(
        session,
        archivo,
        existentes,
        precios,
        resultado,
        org_id=org_id,
        presupuesto_id=capitulo.presupuesto_id,
        codigo_raiz=archivo.raiz.codigo,
        parent_id=capitulo.id,
        orden_capitulos_inicial=int(orden_cap + 1) if orden_cap is not None else 0,
        orden_partidas_inicial=int(orden_part + 1) if orden_part is not None else 0,
    )
    return resultado


async def importar_en_raiz(
    session: AsyncSession,
    archivo: ArchivoBC3,
    presupuesto_id: uuid.UUID,
    *,
    estrategia: EstrategiaCodigos = EstrategiaCodigos.OMITIR,
) -> ResultadoImportacion:
    """Igual que `importar_bajo_capitulo`, pero arrastrando el BC3 sobre la
    fila raíz del presupuesto en vez de sobre un capítulo: los capítulos del
    fichero se cuelgan como capítulos de primer nivel, detrás de los que ya
    hubiera. Las partidas que el fichero traiga sueltas en su raíz (sin un
    capítulo que las envuelva) se ignoran, igual que en `importar()` — una
    partida siempre necesita un capítulo y no le inventamos uno.
    """
    org_id = require_organization_id()
    resultado, existentes, precios = await _parsear_y_subir_conceptos(session, archivo, estrategia)
    if resultado.ciclos or not archivo.es_presupuesto or archivo.raiz is None:
        return resultado

    presupuesto = await session.scalar(
        select(Presupuesto).where(
            Presupuesto.id == presupuesto_id, Presupuesto.organization_id == org_id
        )
    )
    if presupuesto is None:
        resultado.incidencias.append("El presupuesto destino no existe")
        return resultado

    orden_cap = await session.scalar(
        select(func.max(Capitulo.orden)).where(
            Capitulo.presupuesto_id == presupuesto_id, Capitulo.parent_id.is_(None)
        )
    )

    resultado.presupuesto_id = presupuesto.id
    await _recorrer_bc3(
        session,
        archivo,
        existentes,
        precios,
        resultado,
        org_id=org_id,
        presupuesto_id=presupuesto.id,
        codigo_raiz=archivo.raiz.codigo,
        parent_id=None,
        orden_capitulos_inicial=int(orden_cap + 1) if orden_cap is not None else 0,
    )
    return resultado


def _fila_concepto(
    org_id: uuid.UUID,
    nuevo_id: uuid.UUID,
    concepto: ConceptoBC3,
    precios: dict[str, Decimal],
    archivo: ArchivoBC3,
) -> dict:
    descompuesto = concepto.codigo in archivo.descomposiciones
    return {
        "id": nuevo_id,
        "organization_id": org_id,
        "codigo": concepto.codigo,
        "tipo": TIPOS_PRECIO[concepto.tipo],
        "naturaleza": NaturalezaConcepto(concepto.naturaleza),
        "unidad": concepto.unidad or "ud",
        "resumen": concepto.resumen or concepto.codigo,
        "texto": concepto.texto,
        "precio": precios.get(concepto.codigo, Decimal("0.00")),
        # Un descompuesto queda ligado a sus hijos; uno sin descomposición
        # conserva el precio del fichero y no lo pisa nadie.
        "origen_precio": (
            OrigenPrecio.DESCOMPOSICION if descompuesto else OrigenPrecio.MANUAL
        ),
        "fecha_precio": concepto.fecha,
        "costes_indirectos": None,
        "activo": True,
        "origen_dato": OrigenDato.FIEBDC3,
        "atributos": {"fiebdc_tipo": concepto.tipo_fiebdc} if concepto.tipo_fiebdc else {},
    }


async def _importar_presupuesto(
    session: AsyncSession,
    archivo: ArchivoBC3,
    conceptos_bd: dict[str, uuid.UUID],
    precios: dict[str, Decimal],
    resultado: ResultadoImportacion,
    *,
    nombre_presupuesto: str | None,
    codigo_presupuesto: str | None,
) -> None:
    from app.modules.presupuestos.presupuesto_service import siguiente_codigo

    org_id = require_organization_id()
    raiz = archivo.raiz
    if raiz is None:
        return

    presupuesto = Presupuesto(
        organization_id=org_id,
        codigo=codigo_presupuesto or await siguiente_codigo(session),
        nombre=nombre_presupuesto or raiz.resumen or archivo.cabecera or "Obra importada",
        descripcion=raiz.texto,
        origen_dato=OrigenDato.FIEBDC3,
    )
    session.add(presupuesto)
    await session.flush()
    resultado.presupuesto_id = presupuesto.id

    await _recorrer_bc3(
        session,
        archivo,
        conceptos_bd,
        precios,
        resultado,
        org_id=org_id,
        presupuesto_id=presupuesto.id,
        codigo_raiz=raiz.codigo,
        parent_id=None,
    )


async def _recorrer_bc3(
    session: AsyncSession,
    archivo: ArchivoBC3,
    conceptos_bd: dict[str, uuid.UUID],
    precios: dict[str, Decimal],
    resultado: ResultadoImportacion,
    *,
    org_id: uuid.UUID,
    presupuesto_id: uuid.UUID,
    codigo_raiz: str,
    parent_id: uuid.UUID | None,
    orden_capitulos_inicial: int = 0,
    orden_partidas_inicial: int = 0,
) -> None:
    """Recorrido recursivo compartido por "crear presupuesto nuevo" y
    "insertar bajo un capítulo existente": arma capítulos/partidas/mediciones
    a partir de `codigo_raiz` hacia abajo, colgando todo de `parent_id`
    (`None` = nivel raíz del presupuesto). Los `orden_*_inicial` solo importan
    en el primer nivel — un capítulo recién creado por este mismo recorrido
    nunca tiene hermanos previos, así que sus hijos siempre empiezan en 0."""
    mediciones = {(m.padre, m.hijo): m for m in archivo.mediciones}

    async def recorrer(
        codigo: str,
        parent_id: uuid.UUID | None,
        profundidad: int,
        orden_cap: int,
        orden_part: int,
    ) -> None:
        if profundidad > 12:
            resultado.incidencias.append(
                f"'{codigo}': jerarquía demasiado profunda, se corta el recorrido"
            )
            return

        for linea in archivo.descomposiciones.get(codigo, []):
            hijo = archivo.conceptos.get(linea.hijo)
            if hijo is None:
                # No debería pasar tras la normalización del parser, pero si
                # el fichero referencia un código que de verdad no existe en
                # ningún ~C, mejor decirlo que perder esa rama en silencio.
                resultado.incidencias.append(
                    f"'{codigo}' referencia a '{linea.hijo}', que no está en el fichero; se omite"
                )
                continue

            if hijo.tipo is TipoConceptoBC3.CAPITULO:
                capitulo = Capitulo(
                    organization_id=org_id,
                    presupuesto_id=presupuesto_id,
                    parent_id=parent_id,
                    codigo=hijo.codigo.rstrip("#") or hijo.codigo,
                    resumen=hijo.resumen or hijo.codigo,
                    texto=hijo.texto,
                    orden=orden_cap,
                )
                session.add(capitulo)
                await session.flush()
                orden_cap += 1
                resultado.capitulos += 1
                await recorrer(hijo.codigo, capitulo.id, profundidad + 1, 0, 0)
                continue

            if parent_id is None:
                # Una partida colgando directamente de la raíz no tiene
                # capítulo; se ignora en vez de inventarle uno.
                resultado.incidencias.append(
                    f"'{hijo.codigo}' cuelga de la raíz sin capítulo; no se importa como partida"
                )
                continue

            medicion = mediciones.get((codigo, hijo.codigo))
            partida = Partida(
                organization_id=org_id,
                presupuesto_id=presupuesto_id,
                capitulo_id=parent_id,
                concepto_id=conceptos_bd.get(hijo.codigo),
                codigo=hijo.codigo,
                resumen=hijo.resumen or hijo.codigo,
                texto=hijo.texto,
                unidad=hijo.unidad or "ud",
                precio=precios.get(hijo.codigo, Decimal("0.00")),
                orden=orden_part,
            )
            session.add(partida)
            await session.flush()
            orden_part += 1
            resultado.partidas += 1

            total = Decimal("0.000")
            if medicion is not None:
                for posicion, fila in enumerate(medicion.lineas):
                    parcial = parcial_de(fila.uds, fila.longitud, fila.anchura, fila.altura)
                    total += parcial
                    session.add(
                        LineaMedicion(
                            organization_id=org_id,
                            partida_id=partida.id,
                            comentario=fila.comentario or None,
                            uds=fila.uds,
                            longitud=fila.longitud,
                            anchura=fila.anchura,
                            altura=fila.altura,
                            parcial=parcial,
                            orden=posicion,
                        )
                    )
                    resultado.lineas_medicion += 1
                # Si el fichero no trae líneas pero sí total, se respeta.
                if not medicion.lineas and medicion.total is not None:
                    total = medicion.total
            else:
                # Sin ~M, el rendimiento de la línea ~D es la medición.
                total = linea.rendimiento * linea.factor

            partida.medicion = redondear_medicion(total)
            partida.importe = redondear_precio(partida.medicion * partida.precio)

    await recorrer(codigo_raiz, parent_id, 0, orden_capitulos_inicial, orden_partidas_inicial)
    await session.flush()
