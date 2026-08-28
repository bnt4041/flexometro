from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ConfiguracionIAOut(BaseModel):
    """Nunca se devuelve la clave real, solo si hay una configurada: es una
    pantalla de superadmin, pero una clave de API no tiene por qué viajar de
    vuelta al navegador una vez guardada."""

    deepseek_configurada: bool
    deepseek_model: str
    deepseek_vision_model: str
    deepseek_base_url: str
    gemini_configurada: bool
    gemini_model: str
    gemini_base_url: str


class ConfiguracionIAUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deepseek_api_key: str | None = None
    deepseek_model: str | None = Field(default=None, min_length=1, max_length=60)
    deepseek_vision_model: str | None = Field(default=None, min_length=1, max_length=60)
    deepseek_base_url: str | None = Field(default=None, min_length=1, max_length=200)
    gemini_api_key: str | None = None
    gemini_model: str | None = Field(default=None, min_length=1, max_length=60)
    gemini_base_url: str | None = Field(default=None, min_length=1, max_length=200)


class ConfiguracionSmtpOut(BaseModel):
    host: str | None
    puerto: int
    usuario: str | None
    remitente: str | None
    usa_tls: bool
    tiene_password: bool


class ConfiguracionSmtpUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    puerto: int | None = Field(default=None, ge=1, le=65535)
    usuario: str | None = None
    password: str | None = None
    remitente: str | None = None
    usa_tls: bool | None = None


class PruebaSmtpIn(BaseModel):
    destinatario: EmailStr


class PruebaSmtpOut(BaseModel):
    """`enviado=False` con `error` relleno no es un fallo del endpoint (sigue
    devolviendo 200): el envío en sí ha fallado, y ese error tal cual lo dio
    el servidor SMTP es precisamente lo que esta pantalla necesita enseñar."""

    enviado: bool
    error: str | None = None


class ConfiguracionPasarelaOut(BaseModel):
    proveedor: str
    vendor_id: str | None
    tiene_api_key: bool
    activa: bool


class ConfiguracionPasarelaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proveedor: str | None = Field(default=None, min_length=1, max_length=20)
    api_key: str | None = None
    vendor_id: str | None = Field(default=None, max_length=60)
    activa: bool | None = None
