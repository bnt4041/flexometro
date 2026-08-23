from enum import StrEnum

from pydantic import BaseModel


class TipoAparicion(StrEnum):
    PRESUPUESTO = "presupuesto"
    OBRA = "obra"
    ALBARAN = "albaran"
    FACTURA = "factura"
    CONCEPTO = "concepto"


class AparicionOut(BaseModel):
    """Una fila de "dónde aparece este tercero" (Fase 46). `titulo` es lo que
    identifica la ficha a simple vista (nombre de la obra, concepto de la
    factura...); `subtitulo` da contexto extra cuando el título por sí solo
    no basta (en qué obra está el albarán, si el precio es preferente)."""

    tipo: TipoAparicion
    id: str
    codigo: str
    titulo: str
    subtitulo: str | None = None
    estado: str | None = None
