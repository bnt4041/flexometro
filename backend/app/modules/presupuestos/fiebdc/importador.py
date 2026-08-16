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

from sqlalchemy import insert, select
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


async def importar(
    session: AsyncSession,
    archivo: ArchivoBC3,
    *,
    estrategia: EstrategiaCodigos = EstrategiaCodigos.OMITIR,
    crear_presupuesto: bool = True,
    nombre_presupuesto: str | None = None,
    codigo_presupuesto: str | None = None,
) -> ResultadoImportacion:
    org_id = require_organization_id()
    resultado = ResultadoImportacion(
        incidencias=[f"línea {i.linea} {i.registro}: {i.detalle}" for i in archivo.incidencias]
    )

    resultado.ciclos = detectar_ciclos(archivo)
    if resultado.ciclos:
        # Con ciclos no se escribe nada: el árbol de precios no sería calculable.
        return resultado

    precios, discrepancias = calcular_precios(archivo)
    resultado.discrepancias = discrepancias

    # --- Conceptos de precio ---

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

    # --- Presupuesto ---

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

    # Mediciones indexadas por el par capítulo/partida al que pertenecen.
    mediciones = {(m.padre, m.hijo): m for m in archivo.mediciones}

    capitulos_bd: dict[str, uuid.UUID] = {}
    partidas: list[Partida] = []

    async def recorrer(codigo: str, parent_id: uuid.UUID | None, profundidad: int) -> None:
        if profundidad > 12:
            resultado.incidencias.append(
                f"'{codigo}': jerarquía demasiado profunda, se corta el recorrido"
            )
            return

        for orden, linea in enumerate(archivo.descomposiciones.get(codigo, [])):
            hijo = archivo.conceptos.get(linea.hijo)
            if hijo is None:
                continue

            if hijo.tipo is TipoConceptoBC3.CAPITULO:
                capitulo = Capitulo(
                    organization_id=org_id,
                    presupuesto_id=presupuesto.id,
                    parent_id=parent_id,
                    codigo=hijo.codigo.rstrip("#") or hijo.codigo,
                    resumen=hijo.resumen or hijo.codigo,
                    texto=hijo.texto,
                    orden=orden,
                )
                session.add(capitulo)
                await session.flush()
                capitulos_bd[hijo.codigo] = capitulo.id
                resultado.capitulos += 1
                await recorrer(hijo.codigo, capitulo.id, profundidad + 1)
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
                presupuesto_id=presupuesto.id,
                capitulo_id=parent_id,
                concepto_id=conceptos_bd.get(hijo.codigo),
                codigo=hijo.codigo,
                resumen=hijo.resumen or hijo.codigo,
                texto=hijo.texto,
                unidad=hijo.unidad or "ud",
                precio=precios.get(hijo.codigo, Decimal("0.00")),
                orden=orden,
            )
            session.add(partida)
            await session.flush()
            partidas.append(partida)
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

    await recorrer(raiz.codigo, None, 0)
    await session.flush()
