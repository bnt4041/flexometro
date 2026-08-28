from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"

    postgres_user: str = "obras"
    postgres_password: str = "obras_dev_password"
    postgres_db: str = "obras"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # Rol de mínimo privilegio con el que la migración deja creado el acceso
    # de la API en tiempo de ejecución: sin SUPERUSER, sin BYPASSRLS. Solo lo
    # usa la propia migración para saber a quién conceder permisos; la API se
    # conecta con `postgres_user`, que en el contenedor `api` ya es este rol.
    app_db_user: str = "obras_app"
    app_db_password: str = ""

    # stub -> principal fijo, sin autenticación; keycloak -> validación de JWT
    auth_backend: Literal["stub", "keycloak"] = "keycloak"
    stub_organization_slug: str = "demo"

    # URL interna: la usa la API para pedir las claves públicas del realm.
    keycloak_server_url: str = "http://keycloak:8080"
    # URL pública: la que ve el navegador. El emisor del token lleva esta, y
    # por eso se aceptan las dos como emisor válido.
    keycloak_public_url: str = "http://localhost:8081"
    keycloak_realm: str = "obras"
    keycloak_client_id: str = "obras-api"
    # Claim del token que dice a qué organización pertenece el usuario.
    keycloak_claim_organizacion: str = "organizacion"

    # Credenciales del admin de arranque del propio Keycloak (las mismas con
    # las que se inicializa el contenedor). El panel de superadmin las usa
    # para crear usuarios de organización vía el API de administración de
    # Keycloak — no hace falta un client de servicio aparte para esto.
    keycloak_admin_username: str = "admin"
    keycloak_admin_password: str = "admin"

    @property
    def jwks_url(self) -> str:
        return (
            f"{self.keycloak_server_url.rstrip('/')}"
            f"/realms/{self.keycloak_realm}/protocol/openid-connect/certs"
        )

    @property
    def emisores_validos(self) -> set[str]:
        return {
            f"{self.keycloak_server_url.rstrip('/')}/realms/{self.keycloak_realm}",
            f"{self.keycloak_public_url.rstrip('/')}/realms/{self.keycloak_realm}",
        }

    # Lista separada por comas en vez de `list[str]` directo: así se escribe
    # en el `.env` como una variable normal (`CORS_ORIGINS=https://...,https://...`)
    # sin tener que dar formato JSON al desplegar en un dominio real.
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173", alias="CORS_ORIGINS"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins_raw.split(",") if origen.strip()]

    # URL pública de la aplicación, para enlaces en correos (bienvenida...).
    frontend_url: str = "http://localhost:5173"

    # n8n es la capa conectora de integraciones externas en todos los
    # proyectos de este stack. Vacío por defecto: sin URL configurada, emitir
    # una factura no intenta notificar a nada y el envío queda "pendiente".
    n8n_webhook_facturas_url: str = ""

    # DeepSeek es el proveedor de IA fijo de este stack. Vacío por defecto: sin
    # clave, el módulo `ia` responde 503 en vez de fallar a medias. Solo viaja
    # al modelo vocabulario estructural (tipos de obra, resúmenes, unidades) —
    # nunca precios ni datos de cliente, ver app/modules/ia/deepseek.py.
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # Visión de DeepSeek: modelo distinto del de texto, pero la MISMA clave y
    # la misma `base_url` (API compatible con la de OpenAI: la imagen viaja
    # como `image_url` con un data: URI en base64).
    deepseek_vision_model: str = "deepseek-v4-flash-vision-exp"

    # Gemini es el proveedor de IA fijo para visión/multimodal en este stack
    # (DeepSeek cubre texto/estructura, ver app/modules/ia/deepseek.py): lectura
    # de planos acotados en Fase 10. Vacío por defecto: sin clave, el endpoint
    # de lectura de planos responde 503.
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-flash-latest"

    # Gestor documental (Fase 30): MinIO self-hosted, compatible con la API S3
    # — mismo motivo que DeepSeek/Gemini para elegir proveedor fijo en vez de
    # soportar varios: es el que corre en este stack. Vacío por defecto: sin
    # endpoint, el módulo `documentos` responde 503 en vez de fallar a medias.
    minio_endpoint_url: str = "http://minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "documentos"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )



@lru_cache
def get_settings() -> Settings:
    return Settings()
