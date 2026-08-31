from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.core.settings_models import ProveedorWhatsApp


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


class ConfiguracionWhatsAppOut(BaseModel):
    """Ni la contraseña del puente ni el token de Meta salen nunca: solo si
    hay uno puesto."""

    proveedor: ProveedorWhatsApp
    activa: bool
    prefijo_pais: str

    base_url: str | None
    usuario: str | None
    device_id: str | None
    tiene_password: bool

    cloud_phone_number_id: str | None
    cloud_version: str
    plantilla_aviso: str | None
    plantilla_codigo: str | None
    idioma_plantilla: str
    tiene_cloud_token: bool


class ConfiguracionWhatsAppUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proveedor: ProveedorWhatsApp | None = None
    activa: bool | None = None
    prefijo_pais: str | None = Field(default=None, min_length=1, max_length=5)

    base_url: str | None = None
    usuario: str | None = None
    password: str | None = None
    device_id: str | None = None

    cloud_phone_number_id: str | None = None
    cloud_token: str | None = None
    cloud_version: str | None = Field(default=None, min_length=2, max_length=10)
    plantilla_aviso: str | None = None
    plantilla_codigo: str | None = None
    idioma_plantilla: str | None = Field(default=None, min_length=2, max_length=10)


class VinculacionWhatsAppOut(BaseModel):
    """Estado del emparejamiento del número."""

    #: Si el proveedor seleccionado se vincula escaneando. La API oficial no
    #: (allí se da de alta el número en Meta), y la pantalla esconde el QR.
    soporta_qr: bool
    vinculado: bool
    #: Qué número o qué cuenta hay detrás, para no mandar desde el móvil que
    #: no toca.
    descripcion: str | None = None
    error: str | None = None


class QrVinculacionOut(BaseModel):
    #: El PNG en base64 listo para un `src`. Se manda la imagen y no la URL
    #: del proveedor porque esa apunta a su propio host, que el navegador de
    #: quien configura no tiene por qué alcanzar.
    imagen: str
    segundos: int
    error: str | None = None


class PruebaWhatsAppIn(BaseModel):
    telefono: str = Field(min_length=6, max_length=30)


class PruebaWhatsAppOut(BaseModel):
    """Como en la prueba de SMTP: `enviado=False` con `error` sigue siendo un
    200, porque lo que ha fallado es el envío, no el endpoint — y ese error
    tal cual lo dio el proveedor es justo lo que hay que enseñar."""

    enviado: bool
    error: str | None = None


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
