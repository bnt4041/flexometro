"""Convertir texto en vectores para poder buscar por significado.

Se usa la API de Gemini, que esta instalación ya tiene configurada y pagada,
en lugar de un modelo local. El motivo es concreto y no ideológico: el
servidor tiene ~1,6 GB de RAM libres, y el modelo multilingüe que de verdad
funciona bien en español ocupa más que eso. El pequeño que cabría deja la
máquina al borde compitiendo con Postgres y Keycloak, y da resultados
mediocres en español.

Coste real: se cobra por tokens de entrada. Una wiki de quinientas páginas se
indexa una vez por menos de un euro, y solo se vuelve a pagar por lo que
cambie.
"""

import asyncio
import logging
import math

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: El vector se pide truncado a 768 dimensiones (`gemini-embedding-001`
#: devuelve 3072 por defecto, pero admite 128/256/512/768/1536/3072). 768 es
#: el equilibrio razonable: la calidad apenas baja y el índice ocupa la cuarta
#: parte. Está fijado en la columna de la tabla, así que cambiarlo obliga a
#: reindexar todo — no es un ajuste suelto.
DIMENSIONES = 768
MODELO = "gemini-embedding-001"

#: Cuántos textos se vectorizan a la vez. La API de este modelo no expone
#: `batchEmbedContents` (solo `embedContent` uno a uno y un batch asíncrono
#: que no compensa para esto), así que se paralelizan las llamadas con un
#: tope para no encadenar cientos de peticiones de golpe al reindexar.
CONCURRENCIA = 8

#: Trozos de texto para indexar. Ni tan cortos que pierdan el contexto ni tan
#: largos que una página entera sea un solo vector y la búsqueda no distinga
#: de qué parte habla.
TAMANO_TROZO = 900
SOLAPE = 150


class SinEmbeddings(Exception):
    """No se puede indexar ahora. Nunca debe tumbar el guardado de la página:
    una wiki sin indexar sigue siendo una wiki."""


def trocear(texto: str) -> list[str]:
    """Parte un texto largo en trozos que se solapan.

    El solape existe porque una frase partida justo por la mitad se pierde
    para la búsqueda: repitiendo el final de cada trozo al principio del
    siguiente, ninguna idea queda cortada en dos sin estar entera en alguno.
    """
    limpio = " ".join((texto or "").split())
    if not limpio:
        return []
    if len(limpio) <= TAMANO_TROZO:
        return [limpio]

    trozos = []
    inicio = 0
    while inicio < len(limpio):
        fin = inicio + TAMANO_TROZO
        if fin < len(limpio):
            # Se corta en un espacio, no a mitad de palabra.
            espacio = limpio.rfind(" ", inicio + TAMANO_TROZO // 2, fin)
            if espacio > inicio:
                fin = espacio
        trozos.append(limpio[inicio:fin].strip())
        if fin >= len(limpio):
            break
        inicio = max(inicio + 1, fin - SOLAPE)
    return [t for t in trozos if t]


async def vectorizar(
    session: AsyncSession, textos: list[str], *, para_consulta: bool = False
) -> list[list[float]]:
    """Los vectores de esos textos, en el mismo orden.

    `para_consulta` cambia el tipo de tarea que se le declara al modelo:
    indexar un documento y preguntar por él no son lo mismo, y decírselo
    mejora bastante los resultados. Es gratis y solo hay que acordarse.
    """
    if not textos:
        return []

    from app.modules.ia.credenciales import credenciales_gemini

    credenciales = await credenciales_gemini(session)
    if not credenciales.api_key:
        raise SinEmbeddings(
            "Falta la clave de Gemini (Administración → Ajustes globales → IA)"
        )

    tarea = "RETRIEVAL_QUERY" if para_consulta else "RETRIEVAL_DOCUMENT"
    base = credenciales.base_url.rstrip("/")
    limite = asyncio.Semaphore(CONCURRENCIA)

    async def uno(cliente: httpx.AsyncClient, texto: str) -> list[float]:
        async with limite:
            try:
                respuesta = await cliente.post(
                    f"{base}/models/{MODELO}:embedContent",
                    # La clave va en cabecera y no en la query: httpx registra
                    # la URL completa en el log, y ahí acabaría el secreto.
                    headers={"x-goog-api-key": credenciales.api_key},
                    json={
                        "model": f"models/{MODELO}",
                        "content": {"parts": [{"text": texto[:8000]}]},
                        "taskType": tarea,
                        "outputDimensionality": DIMENSIONES,
                    },
                )
            except httpx.HTTPError as exc:
                raise SinEmbeddings(f"No se ha podido contactar con Gemini: {exc}") from exc

        if respuesta.status_code >= 400:
            detalle = respuesta.text[:300]
            try:
                detalle = respuesta.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            raise SinEmbeddings(f"Gemini rechazó la petición: {detalle}")

        valores = (respuesta.json().get("embedding") or {}).get("values")
        if not valores or len(valores) != DIMENSIONES:
            raise SinEmbeddings("Gemini ha devuelto un vector con otra longitud")
        return _normalizar(valores)

    async with httpx.AsyncClient(timeout=60.0) as cliente:
        return list(await asyncio.gather(*(uno(cliente, t) for t in textos)))


def _normalizar(valores: list[float]) -> list[float]:
    """Deja el vector de módulo 1.

    Hace falta porque al pedir menos dimensiones de las que el modelo produce
    se devuelve el vector truncado, y truncar rompe la norma. Con la distancia
    coseno de pgvector eso desordena los resultados de forma sutil: parecen
    razonables pero no son los mejores.
    """
    norma = math.sqrt(sum(v * v for v in valores))
    if norma == 0:
        return valores
    return [v / norma for v in valores]
