"""Campos libres (Fase 21) — extrafields al estilo Dolibarr, pero sin
`ALTER TABLE` dinámico: en vez de añadir una columna real por cada campo que
un admin define (lo que Dolibarr sí hace, y que aquí pelearía con Alembic y
con RLS), se guardan como filas en un patrón EAV con dos tablas:

- `definicion`: qué campos existen para cada tipo de entidad, a nivel cuenta
  (mismo alcance que el diccionario — un campo se define una vez para toda
  la cuenta). Sin RLS: cuenta_id, no organization_id, igual que
  `core.entrada_diccionario`.
- `valor`: el valor de cada campo en un registro concreto. CON RLS por
  organización, como cualquier tabla de negocio — a diferencia de
  `definicion`, aquí sí hay datos reales de una organización.

`entidad_id` no lleva FK real a la tabla de negocio correspondiente (un
tercero, una partida...): habría que acoplar este módulo a siete módulos de
negocio distintos para una comprobación que no protege nada que RLS no
proteja ya (el valor solo es visible/escribible dentro de la propia
organización); si `entidad_id` no corresponde a ningún registro real o de
otra organización, el valor queda ahí, inerte, nunca se cruza con nada.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "campos_libres"


class EntidadCampoLibre(StrEnum):
    TERCERO = "tercero"
    PRODUCTO = "producto"
    OBRA = "obra"
    PRESUPUESTO = "presupuesto"
    CAPITULO = "capitulo"
    PARTIDA = "partida"
    LINEA_MEDICION = "linea_medicion"
    ASIGNACION = "asignacion"
    PARTE_TRABAJO = "parte_trabajo"


class TipoCampoLibre(StrEnum):
    TEXTO = "texto"
    NUMERO = "numero"
    FECHA = "fecha"
    BOOLEANO = "booleano"
    SELECT = "select"


class CampoLibreDefinicion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "definicion"
    __table_args__ = (
        UniqueConstraint("cuenta_id", "entidad", "clave", name="campo_libre_definicion_unique"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("core.cuenta.id", ondelete="CASCADE"), nullable=False
    )
    entidad: Mapped[EntidadCampoLibre] = mapped_column(
        enum_column(EntidadCampoLibre, "entidad_campo_libre"), nullable=False
    )
    clave: Mapped[str] = mapped_column(String(64), nullable=False)
    etiqueta: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[TipoCampoLibre] = mapped_column(
        enum_column(TipoCampoLibre, "tipo_campo_libre"), nullable=False, default=TipoCampoLibre.TEXTO
    )
    # Solo relevante si tipo == 'select': lista de opciones ["Opción A", ...].
    opciones: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    requerido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CampoLibreValor(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    __tablename__ = "valor"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "entidad", "entidad_id", "definicion_id", name="campo_libre_valor_unique"
        ),
        {"schema": SCHEMA},
    )

    entidad: Mapped[EntidadCampoLibre] = mapped_column(
        enum_column(EntidadCampoLibre, "entidad_campo_libre"), nullable=False
    )
    entidad_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    definicion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.definicion.id", ondelete="CASCADE"), nullable=False
    )
    # Todo se guarda como texto y se interpreta según `definicion.tipo` al
    # leer — mismo motivo que `PatronNumeracion`/diccionario: no hay ninguna
    # columna tipada por definición porque las definiciones no son fijas.
    valor: Mapped[str | None] = mapped_column(Text, nullable=True)
