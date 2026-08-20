"""Cálculo del presupuesto: mediciones, importes y el encadenado PEM → PEC."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TIPO_IVA_PORCENTAJE
from app.core.redondeo import redondear_medicion, redondear_precio
from app.core.tenancy import require_organization_id
from app.modules.presupuestos.calculo import PROFUNDIDAD_MAXIMA
from app.modules.presupuestos.models import Concepto
from app.modules.presupuestos.models_presupuesto import (
    Capitulo,
    LineaMedicion,
    MetodoCalculo,
    Partida,
    PartidaDescomposicion,
    Presupuesto,
)


def parcial_de(
    uds: Decimal | None,
    longitud: Decimal | None,
    anchura: Decimal | None,
    altura: Decimal | None,
    *,
    expresion: str | None = None,
    valores: dict | None = None,
) -> Decimal:
    """Parcial de una línea de medición.

    Las dimensiones no informadas valen 1, no 0: una línea con solo `uds = 5`
    mide 5. Un cero explícito sí anula la línea, que es lo que se espera al
    teclear un 0 a propósito.

    Con fórmula (Fase 37) el parcial es `uds` por el resultado de la expresión,
    y longitud/anchura/altura se ignoran: la fórmula ya dice cómo se mide. `uds`
    sigue multiplicando para poder medir "5 triángulos iguales" sin repetir la
    línea cinco veces.
    """
    if expresion:
        # Import local: `formulas` no depende de nada de aquí, pero mantenerlo
        # dentro evita un import circular si algún día lo necesitara.
        from app.modules.presupuestos.formulas import evaluar

        resultado = evaluar(expresion, valores or {})
        return redondear_medicion((uds if uds is not None else Decimal("1")) * resultado)

    factores = [f for f in (uds, longitud, anchura, altura) if f is not None]
    if not factores:
        return Decimal("0.000")
    producto = Decimal("1")
    for factor in factores:
        producto *= factor
    return redondear_medicion(producto)


async def recalcular_partida(session: AsyncSession, partida: Partida) -> None:
    """Vuelve a sumar la medición y el importe de una partida.

    Ojo: solo se toca la medición si la partida TIENE desglose. Sin líneas de
    medición, el valor guardado es el que alguien tecleó a mano en la rejilla
    (Fase 33), y recalcularlo desde una lista vacía lo pondría a cero — así que
    cualquier edición posterior de la partida borraría su medición en silencio.
    """
    filas = await session.execute(
        select(LineaMedicion.parcial).where(LineaMedicion.partida_id == partida.id)
    )
    parciales = [fila[0] for fila in filas.all()]
    if parciales:
        partida.medicion = redondear_medicion(sum(parciales, Decimal("0.000")))
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    await session.flush()


async def precio_desde_descomposicion_propia(
    session: AsyncSession, partida: Partida
) -> Decimal | None:
    """Precio de una partida que lleva su propio descompuesto (Fase 34).

    Mismo redondeo por línea que `calculo._precio_desde_descomposicion`: es lo
    que hace que el descompuesto impreso cuadre columna a columna. Devuelve
    None si la partida no tiene descomposición propia, para que quien llame
    sepa que sigue el precio del banco.
    """
    filas = await session.execute(
        select(
            PartidaDescomposicion.rendimiento,
            PartidaDescomposicion.factor,
            PartidaDescomposicion.precio,
        ).where(PartidaDescomposicion.partida_id == partida.id)
    )
    lineas = filas.all()
    if not lineas:
        return None

    coste_directo = Decimal("0.00")
    for rendimiento, factor, precio in lineas:
        coste_directo += redondear_precio(rendimiento * factor * precio)

    if partida.costes_indirectos:
        porcentaje = Decimal("1") + partida.costes_indirectos / Decimal("100")
        return redondear_precio(coste_directo * porcentaje)
    return redondear_precio(coste_directo)


async def recalcular_desde_descomposicion(
    session: AsyncSession, partida: Partida
) -> None:
    """Rehace el precio (y con él el importe) de una partida independizada."""
    nuevo = await precio_desde_descomposicion_propia(session, partida)
    if nuevo is None:
        return
    partida.precio = nuevo
    partida.importe = redondear_precio(partida.medicion * partida.precio)
    await session.flush()


def _precio_del_cuadro():
    """Subconsulta escalar con el precio actual del concepto de cada partida."""
    return (
        select(Concepto.precio)
        .where(Concepto.id == Partida.concepto_id)
        .scalar_subquery()
    )


async def _traer_precios(session: AsyncSession, condiciones: list) -> int:
    precio_actual = _precio_del_cuadro()
    # Una partida con descompuesto propio (Fase 34) ya no sigue al banco: su
    # precio sale de sus propias líneas, y dejar que la cascada lo pisara
    # tiraría por tierra justamente el cambio que el usuario pidió aplicar
    # "solo en esta partida".
    independizada = (
        select(PartidaDescomposicion.id)
        .where(PartidaDescomposicion.partida_id == Partida.id)
        .exists()
    )
    resultado = await session.execute(
        update(Partida)
        .where(
            Partida.concepto_id.is_not(None),
            Partida.precio != precio_actual,
            ~independizada,
            *condiciones,
        )
        .values(
            precio=precio_actual,
            importe=func.round(Partida.medicion * precio_actual, 2),
        )
    )
    return resultado.rowcount or 0


async def propagar_a_partidas(
    session: AsyncSession, conceptos_modificados: list[uuid.UUID]
) -> int:
    """Lleva el precio del cuadro a las partidas que lo usan.

    Solo alcanza a los presupuestos sin bloquear: uno emitido conserva el
    precio con el que se firmó. Es el último tramo de la cascada
    suministro → básico → auxiliar → unitario → partida.
    """
    if not conceptos_modificados:
        return 0

    org_id = require_organization_id()
    sin_bloquear = (
        select(Presupuesto.id)
        .where(
            Presupuesto.organization_id == org_id,
            Presupuesto.precios_bloqueados.is_(False),
        )
        .scalar_subquery()
    )
    return await _traer_precios(
        session,
        [
            Partida.organization_id == org_id,
            Partida.concepto_id.in_(conceptos_modificados),
            Partida.presupuesto_id.in_(sin_bloquear),
        ],
    )


async def partidas_desactualizadas(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[tuple[uuid.UUID, Decimal, Decimal]]:
    """Partidas cuyo precio ya no coincide con el del cuadro de precios.

    Solo puede pasar con los precios bloqueados: en los demás la cascada las
    mantiene al día. Devuelve (partida_id, precio en la partida, precio actual).
    """
    org_id = require_organization_id()
    # Las independizadas (Fase 34) no están "desactualizadas": se apartaron del
    # banco a propósito, y avisar de ellas sería ruido.
    independizada = (
        select(PartidaDescomposicion.id)
        .where(PartidaDescomposicion.partida_id == Partida.id)
        .exists()
    )
    filas = await session.execute(
        select(Partida.id, Partida.precio, Concepto.precio)
        .join(Concepto, Concepto.id == Partida.concepto_id)
        .where(
            Partida.presupuesto_id == presupuesto_id,
            Partida.organization_id == org_id,
            Partida.precio != Concepto.precio,
            ~independizada,
        )
        .order_by(Partida.orden)
    )
    return [(fila[0], fila[1], fila[2]) for fila in filas.all()]


async def sincronizar_precios(session: AsyncSession, presupuesto_id: uuid.UUID) -> int:
    """Trae los precios actuales del cuadro a un presupuesto, aunque esté
    bloqueado. Es una acción explícita, nunca automática."""
    org_id = require_organization_id()
    return await _traer_precios(
        session,
        [
            Partida.organization_id == org_id,
            Partida.presupuesto_id == presupuesto_id,
        ],
    )


# --- Venta (Fase 35) ---


class PorcentajeImposible(Exception):
    pass


# `porcentaje_metodo`, `gastos_generales` y `beneficio_industrial` son
# columnas `Numeric(5, 2)`: como mucho 3 dígitos enteros, así que 999.99 es lo
# más grande que aceptan sin desbordar.
_LIMITE_PORCENTAJE = Decimal("999.99")


def venta_unitaria(coste: Decimal, metodo: MetodoCalculo, porcentaje: Decimal) -> Decimal:
    """Precio de venta de una unidad a partir de su coste.

    La diferencia entre los dos métodos comerciales está en sobre qué se
    calcula el porcentaje, y es justo donde se equivoca todo el mundo: un 20 %
    "sobre el coste" convierte 100 en 120, mientras que un 20 % "de beneficio
    final" convierte 100 en 125, porque el beneficio es el 20 % de la venta,
    no del coste.
    """
    if metodo == MetodoCalculo.INCREMENTO_SOBRE_COSTE:
        return redondear_precio(coste * (Decimal("1") + porcentaje / Decimal("100")))
    if metodo == MetodoCalculo.BENEFICIO_FINAL:
        if porcentaje >= Decimal("100"):
            raise PorcentajeImposible(
                "Un beneficio final del 100 % o más no tiene solución: el coste nunca llegaría a cubrirse"
            )
        return redondear_precio(coste / (Decimal("1") - porcentaje / Decimal("100")))
    return coste


def resolver_porcentaje_objetivo(
    metodo: MetodoCalculo,
    gastos_generales_actual: Decimal,
    beneficio_industrial_actual: Decimal,
    coste_libre: Decimal,
    objetivo_libre: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Despeja el único porcentaje del método que, aplicado por igual a
    `coste_libre`, deja la venta en `objetivo_libre` — la parte de un reajuste
    (Fase 38) que decide "a qué fijo se sube", separada de tocar partidas para
    poder probarla sin base de datos.

    Devuelve `(porcentaje_metodo, gastos_generales, beneficio_industrial)`:
    los dos últimos solo importan de verdad en el clásico, que reparte el
    recargo entre GG y BI a prorrata de como estaban (si los dos estaban a
    cero, todo va a gastos generales, por hacer algo determinista antes que
    inventar una proporción).

    Incremento sobre coste y el clásico comparten fórmula —ambos son un
    recargo sobre el coste—, así que se despeja igual. Beneficio final es
    distinto porque su porcentaje es el margen sobre la propia venta, no un
    recargo sobre el coste, así que hace falta un paso más de conversión:
    venta = coste·(1+recargo/100) = coste/(1-margen/100) despeja a
    margen = 100·recargo/(100+recargo).

    El recargo puede salir negativo (vender por debajo de coste): no se
    fuerza a 0, para acercarse lo más posible al objetivo pedido en vez de
    negarse a intentarlo. Solo se rechaza cuando el método no tiene ningún
    porcentaje capaz de representarlo (`PorcentajeImposible`).
    """
    if coste_libre <= 0:
        raise PorcentajeImposible("No hay coste sobre el que calcular un porcentaje")

    recargo_combinado = redondear_precio(
        (objetivo_libre / coste_libre - Decimal("1")) * Decimal("100")
    )

    if metodo == MetodoCalculo.BENEFICIO_FINAL:
        denominador = Decimal("100") + recargo_combinado
        if denominador <= 0:
            raise PorcentajeImposible(
                "El objetivo pide vender muy por debajo del coste: este método no tiene "
                "un porcentaje que lo represente"
            )
        porcentaje = redondear_precio(Decimal("100") * recargo_combinado / denominador)
        if porcentaje >= Decimal("100"):
            raise PorcentajeImposible(
                "El objetivo implica un margen del 100 % o más: no tiene solución con este método"
            )
        return porcentaje, gastos_generales_actual, beneficio_industrial_actual

    # Solo para incremento sobre coste y el clásico: su porcentaje (o el GG+BI
    # combinado) se guarda tal cual en una columna `Numeric(5,2)`, que no
    # admite valores de magnitud 1000 o más. Beneficio final no pasa por
    # aquí —el suyo ya queda acotado por debajo de 100 más arriba—, así que
    # un objetivo desproporcionado frente al coste solo bloquea a estos dos.
    if abs(recargo_combinado) > _LIMITE_PORCENTAJE:
        raise PorcentajeImposible(
            f"El objetivo pide un {'incremento' if recargo_combinado >= 0 else 'descuento'} "
            f"de más del {_LIMITE_PORCENTAJE} % sobre el coste: revisa que sea el valor correcto"
        )

    if metodo == MetodoCalculo.CLASICO:
        anterior = gastos_generales_actual + beneficio_industrial_actual
        if anterior > 0:
            gg_nuevo = redondear_precio(recargo_combinado * gastos_generales_actual / anterior)
        else:
            gg_nuevo = recargo_combinado
        bi_nuevo = redondear_precio(recargo_combinado - gg_nuevo)
        return redondear_precio(gg_nuevo + bi_nuevo), gg_nuevo, bi_nuevo

    return recargo_combinado, gastos_generales_actual, beneficio_industrial_actual


def metodo_de(presupuesto: Presupuesto) -> tuple[MetodoCalculo, Decimal]:
    """Método y porcentaje efectivos.

    Un `Presupuesto` recién construido en memoria todavía no tiene aplicados
    los valores por defecto de la columna (SQLAlchemy los pone al insertar),
    así que aquí llegan a None. Se tratan como el método clásico, que es lo
    que dice el `default` de la tabla.
    """
    return (
        presupuesto.metodo_calculo or MetodoCalculo.CLASICO,
        presupuesto.porcentaje_metodo if presupuesto.porcentaje_metodo is not None else Decimal("0"),
    )


def venta_de_presupuesto(presupuesto: Presupuesto, coste: Decimal) -> Decimal:
    """Venta unitaria según el método del presupuesto. En el clásico, los
    gastos generales y el beneficio industrial se reparten proporcionalmente
    sobre cada partida, que es lo que hace que la suma de ventas cuadre con el
    PEC de toda la vida."""
    metodo, porcentaje = metodo_de(presupuesto)
    if metodo == MetodoCalculo.CLASICO:
        recargo = presupuesto.gastos_generales + presupuesto.beneficio_industrial
        return redondear_precio(coste * (Decimal("1") + recargo / Decimal("100")))
    return venta_unitaria(coste, metodo, porcentaje)


def aplicar_venta(presupuesto: Presupuesto, partida: Partida) -> None:
    """Recalcula la venta de una partida, respetando el candado.

    Una partida bloqueada conserva su precio de venta pase lo que pase: es
    justamente para eso, para que cambiar los porcentajes o reajustar el
    presupuesto no se lleve por delante un precio ya pactado.
    """
    if not partida.venta_bloqueada:
        partida.precio_venta = venta_de_presupuesto(presupuesto, partida.precio)
    partida.importe_venta = redondear_precio(partida.medicion * partida.precio_venta)


async def recalcular_ventas(session: AsyncSession, presupuesto: Presupuesto) -> int:
    """Rehace la venta de todas las partidas del presupuesto. Devuelve cuántas
    ha tocado (las bloqueadas solo se les refresca el importe)."""
    org_id = require_organization_id()
    filas = (
        await session.execute(
            select(Partida).where(
                Partida.presupuesto_id == presupuesto.id,
                Partida.organization_id == org_id,
            )
        )
    ).scalars()
    tocadas = 0
    for partida in filas:
        antes = (partida.precio_venta, partida.importe_venta)
        aplicar_venta(presupuesto, partida)
        if (partida.precio_venta, partida.importe_venta) != antes:
            tocadas += 1
    await session.flush()
    return tocadas


def estado_venta(coste: Decimal, venta: Decimal, objetivo: Decimal) -> str:
    """Semáforo del precio de venta: `perdida` si no cubre el coste, `bajo` si
    cubre pero se queda por debajo de lo que tocaría según el método, y `ok`
    si llega o lo supera."""
    if venta < coste:
        return "perdida"
    if venta < objetivo:
        return "bajo"
    return "ok"


# --- Totales ---


class Totales:
    """Del coste al total, por el método que tenga elegido el presupuesto.

    En el clásico es el encadenado español de siempre: PEM (ejecución
    material) → + gastos generales + beneficio industrial → PEC sin IVA
    → + IVA → total. En los otros dos, la venta sale de aplicar el porcentaje
    del método sobre el coste (ver `venta_unitaria`).

    `venta_sin_iva` es siempre la suma real de los importes de venta de las
    partidas, no una fórmula sobre el total: si alguna venta está bloqueada a
    mano, el encadenado teórico y la realidad dejan de coincidir, y esa
    diferencia se expone aparte en `ajuste_manual` en vez de disimularse.
    """

    def __init__(
        self,
        presupuesto: Presupuesto,
        pem: Decimal,
        venta_sin_iva: Decimal | None = None,
    ) -> None:
        self.metodo, self.porcentaje_metodo = metodo_de(presupuesto)
        self.pem = redondear_precio(pem)
        self.coste = self.pem

        if self.metodo == MetodoCalculo.CLASICO:
            self.gastos_generales = redondear_precio(
                self.pem * presupuesto.gastos_generales / Decimal("100")
            )
            self.beneficio_industrial = redondear_precio(
                self.pem * presupuesto.beneficio_industrial / Decimal("100")
            )
        else:
            self.gastos_generales = Decimal("0.00")
            self.beneficio_industrial = Decimal("0.00")

        teorico = self.pem + self.gastos_generales + self.beneficio_industrial
        if self.metodo != MetodoCalculo.CLASICO:
            try:
                teorico = venta_unitaria(self.pem, self.metodo, self.porcentaje_metodo)
            except PorcentajeImposible:
                teorico = self.pem

        # Sin ventas calculadas (llamadas antiguas) se usa el encadenado
        # teórico, que es lo que hacía esta clase antes de la Fase 35.
        self.pec_sin_iva = redondear_precio(venta_sin_iva) if venta_sin_iva is not None else teorico
        self.venta_sin_iva = self.pec_sin_iva
        self.ajuste_manual = self.pec_sin_iva - teorico
        self.incremento = self.pec_sin_iva - self.coste
        self.margen = self.incremento
        self.margen_pct = (
            redondear_precio(self.margen * Decimal("100") / self.pec_sin_iva)
            if self.pec_sin_iva
            else Decimal("0.00")
        )

        porcentaje_iva = Decimal(TIPO_IVA_PORCENTAJE[presupuesto.tipo_iva])
        # Con inversión del sujeto pasivo la factura va sin IVA: lo
        # autorrepercute el destinatario.
        if presupuesto.inversion_sujeto_pasivo:
            porcentaje_iva = Decimal("0")
        self.porcentaje_iva = porcentaje_iva
        self.iva = redondear_precio(self.pec_sin_iva * porcentaje_iva / Decimal("100"))
        self.total = self.pec_sin_iva + self.iva

    def como_dict(self) -> dict:
        return {
            "metodo": self.metodo,
            "porcentaje_metodo": self.porcentaje_metodo,
            "coste": self.coste,
            "pem": self.pem,
            "gastos_generales": self.gastos_generales,
            "beneficio_industrial": self.beneficio_industrial,
            "ajuste_manual": self.ajuste_manual,
            "incremento": self.incremento,
            "venta_sin_iva": self.venta_sin_iva,
            "pec_sin_iva": self.pec_sin_iva,
            "porcentaje_iva": self.porcentaje_iva,
            "iva": self.iva,
            "total": self.total,
            "margen": self.margen,
            "margen_pct": self.margen_pct,
        }


async def cargar_estructura(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> tuple[list[Capitulo], list[Partida]]:
    """Capítulos y partidas del presupuesto, en dos consultas.

    Se carga entero y se agrega en memoria: un presupuesto tiene cientos de
    filas, no millones, y el árbol en Python se lee mucho mejor que una CTE
    recursiva con agregación ascendente.
    """
    org_id = require_organization_id()
    capitulos = (
        await session.execute(
            select(Capitulo)
            .where(
                Capitulo.presupuesto_id == presupuesto_id,
                Capitulo.organization_id == org_id,
            )
            .order_by(Capitulo.orden, Capitulo.codigo)
        )
    ).scalars()
    partidas = (
        await session.execute(
            select(Partida)
            .where(
                Partida.presupuesto_id == presupuesto_id,
                Partida.organization_id == org_id,
            )
            .order_by(Partida.orden, Partida.codigo)
        )
    ).scalars()
    return list(capitulos), list(partidas)


def importes_por_capitulo(
    capitulos: list[Capitulo], partidas: list[Partida]
) -> dict[uuid.UUID, Decimal]:
    """Importe acumulado de cada capítulo, incluidos sus subcapítulos."""
    directo: dict[uuid.UUID, Decimal] = {c.id: Decimal("0.00") for c in capitulos}
    for partida in partidas:
        if partida.capitulo_id in directo:
            directo[partida.capitulo_id] += partida.importe

    hijos: dict[uuid.UUID | None, list[Capitulo]] = {}
    for capitulo in capitulos:
        hijos.setdefault(capitulo.parent_id, []).append(capitulo)

    acumulado: dict[uuid.UUID, Decimal] = {}

    def sumar(capitulo: Capitulo) -> Decimal:
        if capitulo.id in acumulado:
            return acumulado[capitulo.id]
        total = directo[capitulo.id]
        for hijo in hijos.get(capitulo.id, []):
            total += sumar(hijo)
        acumulado[capitulo.id] = redondear_precio(total)
        return acumulado[capitulo.id]

    for capitulo in capitulos:
        sumar(capitulo)
    return acumulado


async def explosion_recursos(
    session: AsyncSession, presupuesto_id: uuid.UUID
) -> list[tuple[Concepto, Decimal, str | None, str | None]]:
    """Explota hacia abajo el árbol de descomposición de TODAS las partidas de
    un presupuesto, para saber cuánto se necesita de cada recurso (material,
    mano de obra...) en total. Dirección inversa de `calculo.donde_se_usa`
    (que sube desde un concepto hasta quién lo contiene); aquí se baja desde
    cada partida hasta sus componentes, acumulando `rendimiento x factor` a lo
    largo de cada cadena y multiplicando por la medición de la partida de
    origen. Mismo criterio de suma que `donde_se_usa` para resolver rombos: un
    material que entra dos veces en el mismo unitario por caminos distintos
    consume el doble, no el mismo una vez.

    Devuelve TODOS los conceptos alcanzados en la descomposición (no solo
    materiales o mano de obra) — filtrar por `naturaleza` es cosa de quien
    llama, esta función no sabe para qué se va a usar el resultado. El
    tercer y cuarto elemento de la tupla son la naturaleza y la unidad
    CONGELADAS de la línea (Fase 38), si alguna partida las corrigió "solo
    aquí" (ver `cambiar_naturaleza_componente`/`cambiar_resumen_componente`);
    `None` si ninguna lo hizo, en cuyo caso quien llama debe caer en las del
    concepto del banco.

    El primer nivel (de cada partida a sus componentes directos) tiene que
    mirar DOS sitios: si la partida se independizó (Fase 34), su descompuesto
    ya no es el del concepto del banco, sino el propio en
    `partida_descomposicion` — mirar solo `descomposicion` dejaría fuera
    cualquier componente añadido o quitado desde ahí, que es exactamente lo
    que hacen los widgets "Descompuesto"/"Recursos humanos"/"Precios
    básicos". Una alzada con descompuesto propio (sin concepto detrás)
    también cuenta desde aquí. Los niveles siguientes, en cambio, siempre
    bajan por `descomposicion`: la independización es de la partida, no de
    los conceptos que cuelgan de ella.
    """
    org_id = require_organization_id()
    consulta = text(
        """
        WITH RECURSIVE bajada(hijo_id, acumulado, profundidad, naturaleza_propia, unidad_propia) AS (
            SELECT pd.hijo_id, pd.rendimiento * pd.factor * p.medicion, 1, pd.naturaleza, pd.unidad
            FROM presupuestos.partida p
            JOIN presupuestos.partida_descomposicion pd ON pd.partida_id = p.id
            WHERE p.presupuesto_id = CAST(:presupuesto_id AS uuid)
              AND pd.hijo_id IS NOT NULL
          UNION ALL
            SELECT d.hijo_id, d.rendimiento * d.factor * p.medicion, 1, NULL, NULL
            FROM presupuestos.partida p
            JOIN presupuestos.descomposicion d ON d.padre_id = p.concepto_id
            WHERE p.presupuesto_id = CAST(:presupuesto_id AS uuid)
              AND p.concepto_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM presupuestos.partida_descomposicion pd2
                WHERE pd2.partida_id = p.id
              )
          UNION ALL
            SELECT d.hijo_id, b.acumulado * d.rendimiento * d.factor, b.profundidad + 1, NULL, NULL
            FROM presupuestos.descomposicion d
            JOIN bajada b ON d.padre_id = b.hijo_id
            WHERE b.profundidad < :max_prof
        )
        SELECT hijo_id, SUM(acumulado), MAX(naturaleza_propia), MAX(unidad_propia)
        FROM bajada
        GROUP BY hijo_id
        """
    )
    filas = (
        await session.execute(
            consulta, {"presupuesto_id": str(presupuesto_id), "max_prof": PROFUNDIDAD_MAXIMA}
        )
    ).all()
    acumulado: dict[uuid.UUID, Decimal] = {fila[0]: fila[1] for fila in filas}
    naturaleza_propia: dict[uuid.UUID, str | None] = {fila[0]: fila[2] for fila in filas}
    unidad_propia: dict[uuid.UUID, str | None] = {fila[0]: fila[3] for fila in filas}
    if not acumulado:
        return []

    conceptos = (
        await session.execute(
            select(Concepto).where(
                Concepto.id.in_(acumulado), Concepto.organization_id == org_id
            )
        )
    ).scalars()
    return sorted(
        (
            (
                concepto,
                acumulado[concepto.id],
                naturaleza_propia.get(concepto.id),
                unidad_propia.get(concepto.id),
            )
            for concepto in conceptos
        ),
        key=lambda par: par[0].codigo,
    )


def venta_total(partidas: list[Partida]) -> Decimal:
    """Suma de los importes de venta de todas las partidas."""
    return redondear_precio(
        sum((p.importe_venta for p in partidas), Decimal("0.00"))
    )


def pem_de(capitulos: list[Capitulo], acumulado: dict[uuid.UUID, Decimal]) -> Decimal:
    """El PEM es la suma de los capítulos raíz; sumar todos contaría dos veces
    los subcapítulos."""
    return redondear_precio(
        sum(
            (acumulado[c.id] for c in capitulos if c.parent_id is None),
            Decimal("0.00"),
        )
    )
