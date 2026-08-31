"""Informes guardados.

Solo la definición, nunca el resultado: un informe guardado tiene que
enseñar los datos de HOY. Cachear filas aquí significaría que dos personas
con permisos distintos podrían ver el mismo número guardado, que es
exactamente lo que el alcance evita al ejecutar.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    AutoriaMixin,
    Base,
    OrganizationMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

SCHEMA = "informes"


class Informe(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "informe"
    __table_args__ = ({"schema": SCHEMA},)

    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Código del catálogo (`fuentes.py`). No es FK, igual que `module_code`.
    fuente: Mapped[str] = mapped_column(String(64), nullable=False)

    dimensiones: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metricas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    filtros: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: `tabla` | `barras` | `lineas`.
    grafico: Mapped[str] = mapped_column(String(20), nullable=False, default="tabla")
    #: Visible para toda la organización o solo para quien lo creó.
    compartido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
