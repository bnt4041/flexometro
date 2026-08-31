from enum import StrEnum


class EstadoVinculo(StrEnum):
    """El vínculo es siempre entre dos organizaciones, nunca a medias.

    Transiciones válidas (ver `service._exigir_transicion`):
    - PENDIENTE -> ACEPTADO / RECHAZADO: solo la organización destino.
    - PENDIENTE -> REVOCADO: solo la organización origen (retira la invitación).
    - ACEPTADO -> REVOCADO: cualquiera de las dos (rompe la conexión).
    - RECHAZADO y REVOCADO son finales: para volver a intentarlo hace falta
      una invitación nueva, no reabrir esta.
    """

    PENDIENTE = "pendiente"
    ACEPTADO = "aceptado"
    RECHAZADO = "rechazado"
    REVOCADO = "revocado"
