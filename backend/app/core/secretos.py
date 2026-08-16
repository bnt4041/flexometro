import secrets
import string

_ALFABETO_PASSWORD = string.ascii_letters + string.digits + "!@#$%"


def generar_password_temporal(longitud: int = 12) -> str:
    return "".join(secrets.choice(_ALFABETO_PASSWORD) for _ in range(longitud))
