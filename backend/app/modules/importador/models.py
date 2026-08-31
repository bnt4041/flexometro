"""Una importación y su instantánea.

Las filas leídas se guardan en la propia importación. Es lo que garantiza que
lo que se importa sea EXACTAMENTE lo que se previsualizó: si se releyera el
fichero en cada paso, entre la vista previa y el «importar» podría haber
cambiado —o no estar—, y nadie sabría por qué salieron otros datos.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import (
    AutoriaMixin,
    Base,
    OrganizationMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.modules.importador.enums import EstadoImportacion

SCHEMA = "importador"


class Importacion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "importacion"
    __table_args__ = ({"schema": SCHEMA},)

    #: Código del catálogo (`destinos.py`). No es FK, igual que `module_code`.
    destino: Mapped[str] = mapped_column(String(64), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)

    estado: Mapped[EstadoImportacion] = mapped_column(
        enum_column(EstadoImportacion, "estado_importacion"),
        nullable=False,
        default=EstadoImportacion.PREPARADA,
    )

    columnas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: La hoja entera, tal como se leyó. Ver el docstring del módulo.
    filas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: `{campo_destino: nombre_de_columna}`.
    mapeo: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Qué pasó con cada fila: `[{fila, estado, detalle}]`. Se guarda entero
    #: porque «han fallado 12» sin decir cuáles ni por qué no sirve de nada.
    resultado: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    creadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    con_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ejecutada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
