from pydantic import BaseModel


class CreditosIAOut(BaseModel):
    consumidos: int
    incluidos: int
    # Sin tarifa asignada (o tarifa sin créditos configurados): no hay cuota
    # que mostrar, el frontend oculta el medidor en vez de pintar "0 de 0".
    sin_tarifa: bool
