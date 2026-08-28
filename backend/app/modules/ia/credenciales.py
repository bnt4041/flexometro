"""Resolución de credenciales de IA: primero lo configurado en
Administración → Ajustes IA (base de datos, editable desde el panel sin
reiniciar), si no lo que traiga el `.env` — así el stack sigue arrancando sin
nada configurado, y cambiar la clave desde el panel no exige tocar
contenedores.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.core import settings_service


@dataclass(frozen=True)
class CredencialesDeepSeek:
    api_key: str
    modelo: str
    base_url: str
    #: Modelo de visión. Va en la misma dataclass y no en una aparte porque
    #: comparte clave y `base_url` con el de texto: lo único que cambia es
    #: qué `model` se manda en la petición.
    modelo_vision: str = ""


@dataclass(frozen=True)
class CredencialesGemini:
    api_key: str
    modelo: str
    base_url: str


async def credenciales_deepseek(session: AsyncSession) -> CredencialesDeepSeek:
    config = await settings_service.obtener_configuracion_ia(session)
    settings = get_settings()
    return CredencialesDeepSeek(
        api_key=config.deepseek_api_key or settings.deepseek_api_key,
        modelo=config.deepseek_model or settings.deepseek_model,
        base_url=config.deepseek_base_url or settings.deepseek_base_url,
        modelo_vision=config.deepseek_vision_model or settings.deepseek_vision_model,
    )


async def credenciales_gemini(session: AsyncSession) -> CredencialesGemini:
    config = await settings_service.obtener_configuracion_ia(session)
    settings = get_settings()
    return CredencialesGemini(
        api_key=config.gemini_api_key or settings.gemini_api_key,
        modelo=config.gemini_model or settings.gemini_model,
        base_url=config.gemini_base_url or settings.gemini_base_url,
    )
