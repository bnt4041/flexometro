"""Página pública de prueba `/testmeter`: reconoce con IA los elementos de una
foto de obra y sus dimensiones reales — ver `escala.py`.

Sin sesión ni organización, igual que la separata de proveedor
(`compras/publico_router.py`), pero sin siquiera un token: es una prueba
abierta, no algo ligado a una obra o una cuenta. Por eso el límite por IP de
`_limitar` en vez del contador por enlace (`MAX_USOS_IA`) que usa la
separata — aquí no hay a quién atarle el contador.
"""

import json
import time
from collections import defaultdict

from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.modules.testmeter.escala import (
    GeminiError,
    MIME_ACEPTADOS,
    ResultadoEscalaOut,
    detectar_escala,
    detectar_escala_deepseek,
)
from app.modules.testmeter.planta import RevisionPlantaOut, revisar_planta

router = APIRouter(prefix="/api/publico/testmeter", tags=["publico"])

MAX_BYTES = 8 * 1024 * 1024
LIMITE_POR_HORA = 40
# Una foto por esquina: un espacio con más vértices que esto no se levanta de
# una sentada, y el tope evita que una sola petición mande decenas de imágenes.
MAX_FOTOS_PLANTA = 12
_usos_por_ip: dict[str, list[float]] = defaultdict(list)


def _limitar(ip: str) -> None:
    ahora = time.monotonic()
    ventana = _usos_por_ip[ip]
    ventana[:] = [t for t in ventana if ahora - t < 3600]
    if len(ventana) >= LIMITE_POR_HORA:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiadas fotos analizadas; prueba de nuevo en un rato",
        )
    ventana.append(ahora)


@router.post("/escala", response_model=ResultadoEscalaOut)
async def escala(
    request: Request,
    fichero: UploadFile = File(...),
    # Seleccionable desde la propia pantalla para poder comparar los dos con
    # la misma foto: el resultado trae `metricas` (ms y tokens) de la llamada.
    # Por defecto DeepSeek: medido en esta tarea, con el modo pensante apagado
    # va ~2,6x más rápido que Gemini, con la misma precisión de caja y bastante
    # más barato por token.
    proveedor: Literal["gemini", "deepseek"] = Form("deepseek"),
) -> ResultadoEscalaOut:
    _limitar(request.client.host if request.client else "desconocido")

    tipo = fichero.content_type or ""
    if tipo not in MIME_ACEPTADOS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Formato de imagen no admitido: {tipo}"
        )

    contenido = bytearray()
    while chunk := await fichero.read(64 * 1024):
        contenido.extend(chunk)
        if len(contenido) > MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Imagen demasiado grande (máx. 8 MB)"
            )
    if not contenido:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Fichero vacío")

    motor = detectar_escala_deepseek if proveedor == "deepseek" else detectar_escala
    try:
        return await motor(bytes(contenido), tipo)
    except GeminiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


async def _leer_acotado(fichero: UploadFile) -> bytes:
    tipo = fichero.content_type or ""
    if tipo not in MIME_ACEPTADOS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Formato de imagen no admitido: {tipo}"
        )
    datos = bytearray()
    while chunk := await fichero.read(64 * 1024):
        datos.extend(chunk)
        if len(datos) > MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Imagen demasiado grande (máx. 8 MB)"
            )
    return bytes(datos)


@router.post("/planta", response_model=RevisionPlantaOut)
async def planta(
    request: Request,
    # Una foto por esquina marcada, en el mismo orden en que se marcaron.
    fotos: list[UploadFile] = File(...),
    # Longitudes de cada muro en metros, como JSON — las midió el AR y aquí
    # viajan solo para que la IA sepa a qué muro asignar cada elemento. No se
    # recalculan: ver la cabecera de `planta.py`.
    muros: str = Form(...),
    proveedor: Literal["gemini", "deepseek"] = Form("deepseek"),
) -> RevisionPlantaOut:
    _limitar(request.client.host if request.client else "desconocido")

    try:
        largos = [float(x) for x in json.loads(muros)]
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "«muros» debe ser un JSON con la lista de longitudes en metros",
        ) from exc
    if len(largos) < 3:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Hacen falta al menos 3 muros"
        )
    if not fotos:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No se ha mandado ninguna foto")
    if len(fotos) > MAX_FOTOS_PLANTA:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Demasiadas fotos (máx. {MAX_FOTOS_PLANTA})",
        )

    imagenes: list[tuple[bytes, str]] = []
    for fichero in fotos:
        datos = await _leer_acotado(fichero)
        if datos:
            imagenes.append((datos, fichero.content_type or "image/jpeg"))
    if not imagenes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Todas las fotos venían vacías")

    try:
        return await revisar_planta(imagenes, largos, proveedor)
    except GeminiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
