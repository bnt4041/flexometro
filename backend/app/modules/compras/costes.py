"""Informe de coste real vs. presupuestado.

Vive en `compras` porque es el único módulo con visibilidad legítima sobre las
tres piezas que hay que cruzar: el presupuesto (a través de `obras`, que
depende de `presupuestos`), la mano de obra real (`obras`) y los materiales
reales (el propio `compras`). `obras` no puede importar `compras` — la
dependencia va al revés — así que este informe no puede vivir allí aunque
hable de "la obra"; por eso su ruta pública (`/api/obras/{obra_id}/costes`) se
registra desde el router de `compras`, no desde el de `obras`.

Cada fila compara cifras **directas** de un capítulo (solo lo que se ha
imputado exactamente a ese capítulo, sin arrastrar subcapítulos): es lo que
permite que la suma de todas las filas cuadre siempre con el total, sin
riesgo de contar dos veces el presupuesto de un capítulo y el de su hijo.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redondeo import redondear_precio
from app.modules.compras.schemas import CosteCapitulo, InformeCosteObra
from app.modules.compras.service import coste_materiales_por_capitulo
from app.modules.obras.service import coste_mano_obra_por_capitulo, obtener_obra_con_presupuesto
from app.modules.presupuestos import presupuesto_calculo as calc


def _fila(
    capitulo_id: uuid.UUID | None,
    codigo: str,
    resumen: str,
    presupuestado: Decimal,
    real_materiales: Decimal,
    real_mano_obra: Decimal,
) -> CosteCapitulo:
    real_total = redondear_precio(real_materiales + real_mano_obra)
    desviacion = redondear_precio(real_total - presupuestado)
    desviacion_pct = (
        (desviacion / presupuestado * Decimal("100")).quantize(Decimal("0.1"))
        if presupuestado
        else None
    )
    return CosteCapitulo(
        capitulo_id=capitulo_id,
        codigo=codigo,
        resumen=resumen,
        presupuestado=presupuestado,
        real_materiales=real_materiales,
        real_mano_obra=real_mano_obra,
        real_total=real_total,
        desviacion=desviacion,
        desviacion_pct=desviacion_pct,
    )


async def informe_coste(session: AsyncSession, obra_id: uuid.UUID) -> InformeCosteObra | None:
    resultado = await obtener_obra_con_presupuesto(session, obra_id)
    if resultado is None:
        return None
    obra, _, _ = resultado

    capitulos, partidas = await calc.cargar_estructura(session, obra.presupuesto_id)

    presupuestado_directo: dict[uuid.UUID, Decimal] = {c.id: Decimal("0.00") for c in capitulos}
    for partida in partidas:
        if partida.capitulo_id in presupuestado_directo:
            presupuestado_directo[partida.capitulo_id] += partida.importe

    materiales = await coste_materiales_por_capitulo(session, obra_id)
    mano_obra = await coste_mano_obra_por_capitulo(session, obra_id)

    filas = [
        _fila(
            capitulo.id,
            capitulo.codigo,
            capitulo.resumen,
            presupuestado_directo[capitulo.id],
            materiales.get(capitulo.id, Decimal("0.00")),
            mano_obra.get(capitulo.id, Decimal("0.00")),
        )
        for capitulo in capitulos
    ]

    real_mat_sin = materiales.get(None, Decimal("0.00"))
    real_mo_sin = mano_obra.get(None, Decimal("0.00"))
    if real_mat_sin or real_mo_sin:
        filas.append(
            _fila(None, "—", "Sin capítulo asignado", Decimal("0.00"), real_mat_sin, real_mo_sin)
        )

    totales = _fila(
        None,
        "",
        "Total",
        redondear_precio(sum(presupuestado_directo.values(), Decimal("0.00"))),
        redondear_precio(sum(materiales.values(), Decimal("0.00"))),
        redondear_precio(sum(mano_obra.values(), Decimal("0.00"))),
    )

    return InformeCosteObra(
        obra_id=obra.id,
        obra_codigo=obra.codigo,
        obra_nombre=obra.nombre,
        capitulos=filas,
        totales=totales,
    )
