"""Recorrer un flujo: del disparador hasta donde llegue.

El grafo se recorre siguiendo la salida que devuelve cada nodo, no todas: en
un nodo de condición solo se sigue una de las dos ramas, y por eso el
histórico guarda POR CUÁL se fue.

Tres guardas, y ninguna es teórica:

- **Tope de pasos.** Un flujo se dibuja en el navegador y nada impide
  conectar un nodo consigo mismo. Sin tope, esa figura ocupa un proceso para
  siempre.
- **Nada de mirar atrás.** Cada nodo se ejecuta como mucho una vez por
  pasada. Es lo que convierte un ciclo en un final, no en un bucle.
- **Un fallo no tumba lo anterior.** Si el cuarto nodo falla, los tres
  primeros ya pasaron —y si mandaron correos, negarlo sería mentir—. La
  ejecución queda `parcial`, que es distinto de `fallida`.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.automatizaciones import nodos
from app.modules.automatizaciones.enums import EstadoEjecucion, EstadoPaso
from app.modules.automatizaciones.expresiones import resolver
from app.modules.automatizaciones.models import Automatizacion, Ejecucion, PasoEjecucion

logger = logging.getLogger(__name__)

#: Cuántos nodos como mucho por pasada. Un flujo real tiene menos de diez;
#: cincuenta deja margen de sobra y corta cualquier figura rara.
MAX_PASOS = 50


def nodos_de(definicion: dict) -> dict[str, dict]:
    return {n["id"]: n for n in (definicion or {}).get("nodos", []) if n.get("id")}


def disparador_de(definicion: dict) -> dict | None:
    """El nodo por el que se empieza. `None` si el flujo no tiene ninguno."""
    for nodo in (definicion or {}).get("nodos", []):
        tipo = nodos.obtener(nodo.get("tipo", ""))
        if tipo and tipo.categoria == "disparador":
            return nodo
    return None


def _siguientes(definicion: dict, nodo_id: str, ruta: str) -> list[str]:
    return [
        c["hasta"]
        for c in (definicion or {}).get("conexiones", [])
        if c.get("desde") == nodo_id
        # Una conexión sin salida declarada se toma como la principal: es lo
        # que pasa con los nodos de una sola salida, que son la mayoría.
        and (c.get("salida") or nodos.SALIDA_PRINCIPAL) == ruta
    ]


async def ejecutar(
    session: AsyncSession,
    automatizacion: Automatizacion,
    *,
    disparador: str,
    entrada: dict[str, Any],
) -> Ejecucion:
    """Una pasada completa. Nunca lanza: el resultado se cuenta en la propia
    ejecución, que es lo que después se puede mirar en pantalla."""
    ejecucion = Ejecucion(
        organization_id=automatizacion.organization_id,
        automatizacion_id=automatizacion.id,
        estado=EstadoEjecucion.EN_CURSO,
        disparador=disparador,
        entrada=entrada,
    )
    session.add(ejecucion)
    await session.flush()

    definicion = automatizacion.definicion or {}
    inicio = disparador_de(definicion)
    if inicio is None:
        ejecucion.estado = EstadoEjecucion.FALLIDA
        ejecucion.error = "El flujo no tiene nodo de disparo"
        ejecucion.terminada_en = datetime.now(UTC)
        await session.flush()
        return ejecucion

    catalogo_nodos = nodos_de(definicion)
    # El contexto arranca con lo que trajo el disparador, bajo su propio
    # nombre: así una expresión puede decir `{{ disparador.titulo }}`.
    contexto: dict[str, Any] = {"disparador": entrada}

    pendientes: list[str] = _siguientes(definicion, inicio["id"], nodos.SALIDA_PRINCIPAL)
    visitados: set[str] = {inicio["id"]}
    orden = 0
    hubo_error = False
    hubo_exito = False

    while pendientes and orden < MAX_PASOS:
        nodo_id = pendientes.pop(0)
        if nodo_id in visitados:
            # Ya pasó por aquí: seguir sería dar vueltas.
            continue
        visitados.add(nodo_id)

        nodo = catalogo_nodos.get(nodo_id)
        if nodo is None:
            continue
        tipo = nodos.obtener(nodo.get("tipo", ""))
        ejecutor = nodos.ejecutor_de(nodo.get("tipo", ""))
        if tipo is None or ejecutor is None:
            orden += 1
            session.add(
                PasoEjecucion(
                    organization_id=automatizacion.organization_id,
                    ejecucion_id=ejecucion.id,
                    nodo_id=nodo_id,
                    tipo_nodo=nodo.get("tipo", "?"),
                    orden=orden,
                    estado=EstadoPaso.ERROR,
                    error=f"Tipo de nodo desconocido: {nodo.get('tipo')}",
                )
            )
            hubo_error = True
            continue

        orden += 1
        arranque = time.monotonic()
        try:
            parametros = resolver(nodo.get("parametros") or {}, contexto)
            salida, ruta = await ejecutor(
                session, automatizacion.organization_id, parametros
            )
            estado_paso, error = EstadoPaso.OK, None
            hubo_exito = True
        except Exception as exc:  # noqa: BLE001
            # Ancho a propósito: un nodo es código de terceros a efectos
            # prácticos (una URL ajena, un dato raro). Que reviente uno no
            # puede tirar el proceso ni perder el rastro de lo anterior.
            logger.warning(
                "Automatización %s, nodo %s: %s", automatizacion.id, nodo_id, exc
            )
            salida, ruta = {}, None
            estado_paso, error = EstadoPaso.ERROR, str(exc)[:1000]
            hubo_error = True

        session.add(
            PasoEjecucion(
                organization_id=automatizacion.organization_id,
                ejecucion_id=ejecucion.id,
                nodo_id=nodo_id,
                tipo_nodo=nodo["tipo"],
                orden=orden,
                estado=estado_paso,
                salida=salida if isinstance(salida, dict) else {"valor": salida},
                ruta=ruta,
                error=error,
                duracion_ms=int((time.monotonic() - arranque) * 1000),
            )
        )

        if error is None:
            contexto[nodo_id] = salida
            pendientes.extend(_siguientes(definicion, nodo_id, ruta))

    if orden >= MAX_PASOS:
        hubo_error = True
        ejecucion.error = f"Se alcanzó el tope de {MAX_PASOS} pasos: ¿hay un ciclo?"

    ejecucion.estado = (
        EstadoEjecucion.PARCIAL
        if hubo_error and hubo_exito
        else EstadoEjecucion.FALLIDA
        if hubo_error
        else EstadoEjecucion.COMPLETADA
    )
    ejecucion.terminada_en = datetime.now(UTC)
    await session.flush()
    # Los pasos se cargan aquí y no cuando alguien los mire: la relación es
    # perezosa, y leerla fuera de un contexto async revienta con
    # `MissingGreenlet`. Quien recibe esta ejecución la quiere entera —para
    # enseñarla o para guardarla— así que se devuelve completa.
    await session.refresh(ejecucion, ["pasos"])
    return ejecucion


def validar(definicion: dict) -> list[str]:
    """Los problemas de un flujo, en lenguaje llano. Vacío = está bien.

    Se avisa en vez de impedir guardar: un flujo a medias es normal mientras
    se monta, y bloquear el guardado obligaría a terminarlo de una sentada."""
    problemas: list[str] = []
    lista = (definicion or {}).get("nodos", [])
    disparadores = [
        n for n in lista if (t := nodos.obtener(n.get("tipo", ""))) and t.categoria == "disparador"
    ]
    if not disparadores:
        problemas.append("Falta el nodo que arranca el flujo.")
    elif len(disparadores) > 1:
        problemas.append("Hay más de un nodo de arranque; solo puede haber uno.")

    conocidos = nodos_de(definicion)
    for conexion in (definicion or {}).get("conexiones", []):
        if conexion.get("desde") not in conocidos or conexion.get("hasta") not in conocidos:
            problemas.append("Hay una conexión que apunta a un nodo que ya no existe.")
            break

    for nodo in lista:
        tipo = nodos.obtener(nodo.get("tipo", ""))
        if tipo is None:
            problemas.append(f"El nodo «{nodo.get('nombre') or nodo.get('id')}» es de un tipo desconocido.")
            continue
        parametros = nodo.get("parametros") or {}
        faltan = [
            c.etiqueta
            for c in tipo.campos
            if c.obligatorio and not str(parametros.get(c.nombre) or "").strip()
        ]
        if faltan:
            problemas.append(
                f"A «{nodo.get('nombre') or tipo.etiqueta}» le falta: {', '.join(faltan)}."
            )
    return problemas
