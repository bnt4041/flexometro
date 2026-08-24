"""Versiones, plantillas y comparación.

Versionar un presupuesto e instanciar una plantilla son la misma operación: una
copia profunda del árbol. Por eso hay un solo motor de copia y no dos caminos
distintos que se desincronicen en cuanto se añada un campo.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    EstadoPresupuesto,
    LineaMedicion,
    Partida,
    Presupuesto,
)

# Campos que se copian tal cual al duplicar. Se enumeran a propósito en vez de
# copiar el objeto entero: así añadir una columna obliga a decidir si viaja con
# la copia o no, en lugar de colarse sin que nadie lo piense.
CAMPOS_COPIABLES = (
    "descripcion",
    "cliente_id",
    "emplazamiento",
    "validez_dias",
    "gastos_generales",
    "beneficio_industrial",
    "tipo_iva",
    "inversion_sujeto_pasivo",
    "tipo_obra",
    "notas",
)


class PresupuestoNoEncontrado(Exception):
    pass


@dataclass
class ArbolPresupuesto:
    """Capítulos, partidas y mediciones ya leídos del origen. Se separa de la
    escritura porque copiar a otra empresa (Fase 45) obliga a leer con la
    organización de origen activa y escribir con la de destino: RLS filtra las
    lecturas por `app.organization_id` y rechaza los INSERT que no casen con
    ella, así que no caben en el mismo tramo."""

    capitulos: list
    partidas: list
    lineas: list


async def _leer_arbol(session: AsyncSession, origen_id: uuid.UUID) -> ArbolPresupuesto:
    capitulos = list(
        (
            await session.execute(
                select(Capitulo)
                .where(Capitulo.presupuesto_id == origen_id)
                .order_by(Capitulo.orden, Capitulo.codigo)
            )
        ).scalars()
    )
    partidas = list(
        (
            await session.execute(
                select(Partida)
                .where(Partida.presupuesto_id == origen_id)
                .order_by(Partida.orden)
            )
        ).scalars()
    )
    lineas = list(
        (
            await session.execute(
                select(LineaMedicion)
                .join(Partida, Partida.id == LineaMedicion.partida_id)
                .where(Partida.presupuesto_id == origen_id)
                .order_by(LineaMedicion.orden)
            )
        ).scalars()
    )
    return ArbolPresupuesto(capitulos=capitulos, partidas=partidas, lineas=lineas)


async def _escribir_arbol(
    session: AsyncSession,
    arbol: ArbolPresupuesto,
    destino: Presupuesto,
    *,
    org_id: uuid.UUID,
    con_mediciones: bool,
) -> None:
    capitulos, partidas, lineas = arbol.capitulos, arbol.partidas, arbol.lineas

    # Los capítulos se crean de arriba abajo para que el padre exista cuando se
    # crea el hijo; el mapa traduce identificadores viejos a nuevos.
    equivalencias: dict[uuid.UUID, uuid.UUID] = {}
    pendientes = list(capitulos)
    while pendientes:
        avance = False
        for capitulo in list(pendientes):
            if capitulo.parent_id is not None and capitulo.parent_id not in equivalencias:
                continue
            nuevo = Capitulo(
                organization_id=org_id,
                presupuesto_id=destino.id,
                parent_id=(
                    equivalencias[capitulo.parent_id]
                    if capitulo.parent_id is not None
                    else None
                ),
                codigo=capitulo.codigo,
                resumen=capitulo.resumen,
                texto=capitulo.texto,
                orden=capitulo.orden,
            )
            session.add(nuevo)
            await session.flush()
            equivalencias[capitulo.id] = nuevo.id
            pendientes.remove(capitulo)
            avance = True
        if not avance:
            # Un padre huérfano dejaría el bucle girando para siempre; los
            # sueltos se cuelgan de la raíz en vez de perderse.
            for capitulo in pendientes:
                nuevo = Capitulo(
                    organization_id=org_id,
                    presupuesto_id=destino.id,
                    parent_id=None,
                    codigo=capitulo.codigo,
                    resumen=capitulo.resumen,
                    texto=capitulo.texto,
                    orden=capitulo.orden,
                )
                session.add(nuevo)
                await session.flush()
                equivalencias[capitulo.id] = nuevo.id
            break

    lineas_por_partida: dict[uuid.UUID, list[LineaMedicion]] = {}
    for linea in lineas:
        lineas_por_partida.setdefault(linea.partida_id, []).append(linea)

    for partida in partidas:
        nueva = Partida(
            organization_id=org_id,
            presupuesto_id=destino.id,
            capitulo_id=equivalencias[partida.capitulo_id],
            concepto_id=partida.concepto_id,
            codigo=partida.codigo,
            resumen=partida.resumen,
            texto=partida.texto,
            unidad=partida.unidad,
            precio=partida.precio,
            medicion=partida.medicion if con_mediciones else Decimal("0.000"),
            importe=partida.importe if con_mediciones else Decimal("0.00"),
            orden=partida.orden,
        )
        session.add(nueva)
        await session.flush()

        if not con_mediciones:
            continue
        for linea in lineas_por_partida.get(partida.id, []):
            session.add(
                LineaMedicion(
                    organization_id=org_id,
                    partida_id=nueva.id,
                    comentario=linea.comentario,
                    uds=linea.uds,
                    longitud=linea.longitud,
                    anchura=linea.anchura,
                    altura=linea.altura,
                    parcial=linea.parcial,
                    orden=linea.orden,
                )
            )
    await session.flush()


async def _copiar_arbol(
    session: AsyncSession,
    origen_id: uuid.UUID,
    destino: Presupuesto,
    *,
    con_mediciones: bool,
) -> None:
    """Leer + escribir dentro de la misma organización — el camino de siempre
    (versión nueva, plantilla). Copiar a otra empresa parte los dos pasos, ver
    `copiar_a_empresa`."""
    arbol = await _leer_arbol(session, origen_id)
    await _escribir_arbol(
        session, arbol, destino, org_id=require_organization_id(), con_mediciones=con_mediciones
    )


async def _cargar(session: AsyncSession, presupuesto_id: uuid.UUID) -> Presupuesto:
    org_id = require_organization_id()
    presupuesto = await session.scalar(
        select(Presupuesto).where(
            Presupuesto.id == presupuesto_id, Presupuesto.organization_id == org_id
        )
    )
    if presupuesto is None:
        raise PresupuestoNoEncontrado("El presupuesto no existe en esta organización")
    return presupuesto


async def nueva_version(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> Presupuesto:
    """Duplica el presupuesto como versión siguiente de su misma línea.

    La versión nueva nace en borrador y con los precios sueltos: es lo que se
    quiere al retomar un presupuesto ya emitido para revisarlo.
    """
    org_id = require_organization_id()
    origen = await _cargar(session, presupuesto_id)

    raiz_id = origen.raiz_id or origen.id
    ultima = await session.scalar(
        select(func.max(Presupuesto.version)).where(
            Presupuesto.organization_id == org_id,
            (Presupuesto.raiz_id == raiz_id) | (Presupuesto.id == raiz_id),
        )
    )
    version = int(ultima or 1) + 1

    raiz = origen if origen.raiz_id is None else await _cargar(session, raiz_id)
    destino = Presupuesto(
        organization_id=org_id,
        codigo=f"{raiz.codigo}.{version}",
        nombre=origen.nombre,
        raiz_id=raiz_id,
        version=version,
        estado=EstadoPresupuesto.BORRADOR,
        precios_bloqueados=False,
        es_plantilla=False,
        fecha=origen.fecha,
        **{campo: getattr(origen, campo) for campo in CAMPOS_COPIABLES},
        **datos_autoria(),
    )
    session.add(destino)
    await session.flush()

    await _copiar_arbol(session, origen.id, destino, con_mediciones=True)
    return destino


async def versiones_de(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[Presupuesto]:
    """Todas las versiones de la misma línea, incluida la consultada."""
    org_id = require_organization_id()
    presupuesto = await _cargar(session, presupuesto_id)
    raiz_id = presupuesto.raiz_id or presupuesto.id

    filas = await session.execute(
        select(Presupuesto)
        .where(
            Presupuesto.organization_id == org_id,
            (Presupuesto.raiz_id == raiz_id) | (Presupuesto.id == raiz_id),
        )
        .order_by(Presupuesto.version)
    )
    return list(filas.scalars())


async def guardar_como_plantilla(
    session: AsyncSession,
    presupuesto_id: uuid.UUID,
    *,
    nombre: str,
    codigo: str,
    tipo_obra: str | None,
    con_mediciones: bool,
) -> Presupuesto:
    """Congela la estructura de un presupuesto para reutilizarla.

    Por defecto se copia sin mediciones: lo reutilizable de un presupuesto es
    qué partidas lleva, no cuántos metros medía aquella obra.
    """
    org_id = require_organization_id()
    origen = await _cargar(session, presupuesto_id)

    campos = {campo: getattr(origen, campo) for campo in CAMPOS_COPIABLES}
    campos["tipo_obra"] = tipo_obra or origen.tipo_obra
    campos["cliente_id"] = None  # una plantilla no pertenece a ningún cliente

    plantilla = Presupuesto(
        organization_id=org_id,
        codigo=codigo,
        nombre=nombre,
        es_plantilla=True,
        estado=EstadoPresupuesto.BORRADOR,
        version=1,
        **campos,
        **datos_autoria(),
    )
    session.add(plantilla)
    await session.flush()

    await _copiar_arbol(session, origen.id, plantilla, con_mediciones=con_mediciones)
    return plantilla


async def instanciar_plantilla(
    session: AsyncSession,
    plantilla_id: uuid.UUID,
    *,
    nombre: str,
    codigo: str,
    cliente_id: uuid.UUID | None,
    emplazamiento: str | None,
) -> Presupuesto:
    org_id = require_organization_id()
    plantilla = await _cargar(session, plantilla_id)

    campos = {campo: getattr(plantilla, campo) for campo in CAMPOS_COPIABLES}
    campos["cliente_id"] = cliente_id
    campos["emplazamiento"] = emplazamiento or plantilla.emplazamiento

    destino = Presupuesto(
        organization_id=org_id,
        codigo=codigo,
        nombre=nombre,
        es_plantilla=False,
        estado=EstadoPresupuesto.BORRADOR,
        version=1,
        **campos,
        **datos_autoria(),
    )
    session.add(destino)
    await session.flush()

    await _copiar_arbol(session, plantilla.id, destino, con_mediciones=True)
    return destino


# --- Copia (Fase 45) ---


class EmpresaDestinoInvalida(Exception):
    pass


async def copiar(
    session: AsyncSession,
    presupuesto_id: uuid.UUID,
    *,
    nombre: str,
    org_destino: uuid.UUID,
    cliente_id: uuid.UUID | None,
    con_mediciones: bool,
) -> Presupuesto:
    """Duplica el presupuesto, opcionalmente en OTRA empresa de la misma
    cuenta. Nace siempre en borrador, con precios sueltos y numeración propia
    de la empresa de destino — es una copia nueva, no una versión ni un
    traslado: el original se queda donde estaba, intacto.

    Copiar en vez de mover es lo que hace esto viable: no hay que reescribir
    `organization_id` de nada (RLS lo prohíbe), ni arrastrar obras,
    certificaciones o facturas colgando, ni arriesgarse a chocar con un
    código ya usado en destino.

    Las referencias a conceptos del banco de precios y al cliente sobreviven
    al salto de empresa porque ambas tablas son "maestros" compartidos entre
    las organizaciones de una misma cuenta (`Cuenta.compartir_maestros`, Fase
    15). Si esa opción estuviera desactivada, la copia seguiría siendo válida
    pero esas referencias quedarían invisibles desde destino — por eso el
    servicio lo comprueba antes.
    """
    from app.core.database import fijar_organizacion_activa
    from app.modules.core.models import Cuenta, Organization

    org_origen = require_organization_id()
    origen = await _cargar(session, presupuesto_id)

    # Todo lo que hay que leer del origen, ANTES de mover el contexto: en
    # cuanto `app.organization_id` apunte a destino, RLS deja de enseñar
    # estas filas.
    arbol = await _leer_arbol(session, presupuesto_id)
    campos = {campo: getattr(origen, campo) for campo in CAMPOS_COPIABLES}
    campos["cliente_id"] = cliente_id

    if org_destino != org_origen:
        destino_valido = await session.scalar(
            select(Organization.id)
            .join(Cuenta, Cuenta.id == Organization.cuenta_id)
            .where(
                Organization.id == org_destino,
                Organization.is_active.is_(True),
                Cuenta.id.in_(
                    select(Organization.cuenta_id).where(Organization.id == org_origen)
                ),
            )
        )
        if destino_valido is None:
            raise EmpresaDestinoInvalida(
                "La empresa de destino no existe o no es de esta misma cuenta"
            )
        await fijar_organizacion_activa(session, org_destino)

    # `presupuesto_service.siguiente_codigo` saca la organización del
    # contexto de la request, que sigue siendo la de origen —
    # `fijar_organizacion_activa` solo mueve la variable de PostgreSQL. Hay
    # que pedir la referencia con la organización de destino explícita, o la
    # copia consumiría un número de la serie de la empresa equivocada.
    from app.modules.presupuestos.presupuesto_service import siguiente_codigo_libre

    codigo = await siguiente_codigo_libre(session, organization_id=org_destino)

    copia = Presupuesto(
        organization_id=org_destino,
        codigo=codigo,
        nombre=nombre,
        es_plantilla=False,
        estado=EstadoPresupuesto.BORRADOR,
        precios_bloqueados=False,
        version=1,
        fecha=origen.fecha,
        **campos,
        **datos_autoria(),
    )
    session.add(copia)
    await session.flush()

    await _escribir_arbol(
        session, arbol, copia, org_id=org_destino, con_mediciones=con_mediciones
    )
    return copia


# --- Comparación ---


@dataclass
class CambioPartida:
    clave: str
    codigo: str
    resumen: str
    unidad: str
    medicion_a: Decimal | None = None
    medicion_b: Decimal | None = None
    precio_a: Decimal | None = None
    precio_b: Decimal | None = None
    importe_a: Decimal = Decimal("0.00")
    importe_b: Decimal = Decimal("0.00")

    @property
    def delta(self) -> Decimal:
        return self.importe_b - self.importe_a


@dataclass
class Comparacion:
    altas: list[CambioPartida] = field(default_factory=list)
    bajas: list[CambioPartida] = field(default_factory=list)
    cambios: list[CambioPartida] = field(default_factory=list)
    sin_cambios: int = 0


async def _indice_partidas(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> dict[str, Partida]:
    """Partidas indexadas por capítulo y código.

    La clave incluye el capítulo porque el mismo unitario puede aparecer en dos
    capítulos distintos del mismo presupuesto y son partidas diferentes.
    """
    filas = await session.execute(
        select(Capitulo.codigo, Partida)
        .join(Capitulo, Capitulo.id == Partida.capitulo_id)
        .where(Partida.presupuesto_id == presupuesto_id)
        .order_by(Capitulo.codigo, Partida.orden)
    )
    indice: dict[str, Partida] = {}
    for capitulo_codigo, partida in filas.all():
        clave = f"{capitulo_codigo}/{partida.codigo}"
        # Si se repite dentro del mismo capítulo, se desempata por posición.
        if clave in indice:
            clave = f"{clave}#{partida.orden}"
        indice[clave] = partida
    return indice


async def comparar(
    session: AsyncSession, a_id: uuid.UUID, b_id: uuid.UUID
) -> Comparacion:
    """Diferencias de A a B, partida a partida."""
    await _cargar(session, a_id)
    await _cargar(session, b_id)

    a = await _indice_partidas(session, a_id)
    b = await _indice_partidas(session, b_id)
    resultado = Comparacion()

    for clave, partida in b.items():
        if clave not in a:
            resultado.altas.append(
                CambioPartida(
                    clave=clave,
                    codigo=partida.codigo,
                    resumen=partida.resumen,
                    unidad=partida.unidad,
                    medicion_b=partida.medicion,
                    precio_b=partida.precio,
                    importe_b=partida.importe,
                )
            )

    for clave, partida in a.items():
        if clave not in b:
            resultado.bajas.append(
                CambioPartida(
                    clave=clave,
                    codigo=partida.codigo,
                    resumen=partida.resumen,
                    unidad=partida.unidad,
                    medicion_a=partida.medicion,
                    precio_a=partida.precio,
                    importe_a=partida.importe,
                )
            )
            continue

        otra = b[clave]
        if partida.medicion == otra.medicion and partida.precio == otra.precio:
            resultado.sin_cambios += 1
            continue

        resultado.cambios.append(
            CambioPartida(
                clave=clave,
                codigo=partida.codigo,
                resumen=partida.resumen,
                unidad=partida.unidad,
                medicion_a=partida.medicion,
                medicion_b=otra.medicion,
                precio_a=partida.precio,
                precio_b=otra.precio,
                importe_a=partida.importe,
                importe_b=otra.importe,
            )
        )

    return resultado
