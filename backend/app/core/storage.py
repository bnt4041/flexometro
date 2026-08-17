"""Cliente de almacenamiento de objetos (Fase 30) para el gestor documental.

MinIO self-hosted es el proveedor fijo de este stack, igual que DeepSeek para
texto y Gemini para visión: no hay abstracción multi-proveedor porque no hace
falta soportar más que el que corre en producción. Se habla con él por su API
compatible con S3 (`boto3`), así que en teoría cualquier S3 real serviría sin
cambiar una línea si el día de mañana se migrara — pero eso no es un objetivo
de diseño, solo una consecuencia de usar el protocolo estándar.

`boto3` es síncrono: cada llamada se envía a un hilo con `asyncio.to_thread`
para no bloquear el loop de eventos, en vez de añadir una segunda librería
async solo para esto.
"""

import asyncio
from functools import lru_cache

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings


class AlmacenNoConfigurado(Exception):
    pass


class ObjetoNoEncontrado(Exception):
    pass


@lru_cache
def _cliente():
    settings = get_settings()
    if not settings.minio_endpoint_url:
        raise AlmacenNoConfigurado("No hay MINIO_ENDPOINT_URL configurado")
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


async def asegurar_bucket() -> None:
    """Crea el bucket si no existe todavía — se llama una vez al arrancar la
    API. No revienta el arranque si MinIO no está disponible: el módulo de
    documentos simplemente fallará en la primera petición real, igual que
    DeepSeek/Gemini sin clave configurada."""
    settings = get_settings()

    def _hacer() -> None:
        cliente = _cliente()
        try:
            cliente.head_bucket(Bucket=settings.minio_bucket)
        except ClientError:
            cliente.create_bucket(Bucket=settings.minio_bucket)

    await asyncio.to_thread(_hacer)


async def subir_objeto(key: str, contenido: bytes, content_type: str) -> None:
    settings = get_settings()

    def _hacer() -> None:
        _cliente().put_object(
            Bucket=settings.minio_bucket, Key=key, Body=contenido, ContentType=content_type
        )

    await asyncio.to_thread(_hacer)


async def descargar_objeto(key: str) -> bytes:
    settings = get_settings()

    def _hacer() -> bytes:
        try:
            return _cliente().get_object(Bucket=settings.minio_bucket, Key=key)["Body"].read()
        except ClientError as exc:
            raise ObjetoNoEncontrado(key) from exc

    return await asyncio.to_thread(_hacer)


async def eliminar_objeto(key: str) -> None:
    settings = get_settings()

    def _hacer() -> None:
        _cliente().delete_object(Bucket=settings.minio_bucket, Key=key)

    await asyncio.to_thread(_hacer)
