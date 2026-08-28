"""Página pública de prueba `/testmeter`: reconoce con IA los elementos de una
foto de obra y sus dimensiones reales — ver `escala.py`.

Sin sesión ni organización, igual que la separata de proveedor
(`compras/publico_router.py`), pero sin siquiera un token: es una prueba
abierta, no algo ligado a una obra o una cuenta. Por eso el límite por IP de
`_limitar` en vez del contador por enlace (`MAX_USOS_IA`) que usa la
separata — aquí no hay a quién atarle el contador.
"""

import time
from collections import defaultdict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.modules.testmeter.escala import (
    GeminiError,
    MIME_ACEPTADOS,
    ResultadoEscalaOut,
    detectar_escala,
)

router = APIRouter(prefix="/api/publico/testmeter", tags=["publico"])

MAX_BYTES = 8 * 1024 * 1024
LIMITE_POR_HORA = 40
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
async def escala(request: Request, fichero: UploadFile = File(...)) -> ResultadoEscalaOut:
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

    try:
        return await detectar_escala(bytes(contenido), tipo)
    except GeminiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
