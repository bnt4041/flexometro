"""Sugerencias de patrón de presupuesto generadas por IA.

Cada sugerencia queda registrada con lo que se envió al modelo — solo
vocabulario estructural, nunca precios ni datos de cliente, ver
`app/modules/ia/deepseek.py` — y con lo que devolvió, ya resuelto contra el
cuadro de precios propio. La sugerencia en sí no es un presupuesto: aceptarla
crea una plantilla real (`presupuestos.presupuesto` con `es_plantilla=True`),
enlazada en `plantilla_id`. Si sigue a NULL, la sugerencia no se ha aceptado
todavía — no hace falta un booleano aparte para eso.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "ia"


class SugerenciaPatron(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "sugerencia_patron"
    __table_args__ = (
        Index("ix_ia_sugerencia_patron_tipo_obra", "organization_id", "tipo_obra"),
        {"schema": SCHEMA},
    )

    tipo_obra: Mapped[str] = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    modelo: Mapped[str] = mapped_column(String(60), nullable=False)

    # Lo que se envió a DeepSeek: solo vocabulario estructural. Se guarda para
    # poder auditar qué ha salido realmente del servidor hacia el exterior.
    estadisticas_enviadas: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # La propuesta del modelo ya resuelta contra el cuadro de precios propio
    # (con concepto_id cuando hay coincidencia por código).
    sugerencia: Mapped[list] = mapped_column(JSONB, nullable=False)

    plantilla_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )


class LecturaPlano(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Lectura de un plano acotado (imagen o PDF) vía Gemini.

    Es la única pieza de `ia` que envía un fichero entero a un proveedor
    externo —a diferencia de `SugerenciaPatron`, aquí no hay forma de evitarlo,
    es la naturaleza propia de "leer un plano"—, así que queda registrada con
    qué fichero se leyó y qué propuso el modelo. `aplicada_en` a NULL significa
    que la lectura todavía no se ha volcado a ninguna línea de medición real;
    no hace falta un booleano aparte para eso, mismo idioma que
    `SugerenciaPatron.plantilla_id`.
    """

    __tablename__ = "lectura_plano"
    __table_args__ = (
        Index("ix_ia_lectura_plano_partida", "organization_id", "partida_id"),
        {"schema": SCHEMA},
    )

    # SET NULL: si la partida se borra más adelante, el registro de auditoría
    # se queda (solo pierde el enlace), no desaparece.
    partida_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.partida.id", ondelete="SET NULL"),
        nullable=True,
    )
    fichero_nombre: Mapped[str] = mapped_column(String(250), nullable=False)
    modelo: Mapped[str] = mapped_column(String(60), nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lo que ha propuesto Gemini, tal cual, antes de que el usuario lo revise
    # o edite en el frontend.
    respuesta_cruda: Mapped[list] = mapped_column(JSONB, nullable=False)
    aplicada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
