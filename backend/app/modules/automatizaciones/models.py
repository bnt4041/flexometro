"""Automatizaciones: flujos de nodos que se disparan solos.

El flujo entero vive en una columna JSONB y no en tablas de nodos y aristas.
Es deliberado: un flujo se edita como una unidad —se arrastran tres nodos, se
cambia una conexión y se guarda— y con tablas normalizadas cada guardado
sería un diff de filas que hay que reconciliar. Además el histórico necesita
saber cómo era el flujo EN EL MOMENTO de ejecutarse, y eso con filas vivas se
pierde en cuanto alguien lo edita.

Lo que sí son tablas es todo lo que pasó: ejecuciones y pasos. Eso es
histórico, se consulta por separado y crece sin parar.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import (
    AutoriaMixin,
    Base,
    OrganizationMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.modules.automatizaciones.enums import EstadoEjecucion, EstadoPaso

SCHEMA = "automatizaciones"


class Automatizacion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "automatizacion"
    __table_args__ = (
        Index("ix_automatizaciones_activa", "organization_id", "activa"),
        {"schema": SCHEMA},
    )

    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: `{"nodos": [...], "conexiones": [...]}`. Ver `nodos.py` para la forma
    #: de cada nodo y `motor.py` para cómo se recorre.
    definicion: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    #: Copia del código del evento que la dispara, sacada de la definición.
    #: Es redundante a propósito: sin ella, saber qué flujos despierta un
    #: evento obligaría a leer y parsear el JSON de TODOS los flujos en cada
    #: hecho que ocurre.
    evento_disparador: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Igual, para el disparador de webhook: el hash de su token.
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Y para el programado: cuándo toca la próxima.
    proxima_ejecucion_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    ejecuciones: Mapped[list["Ejecucion"]] = relationship(
        back_populates="automatizacion", cascade="all, delete-orphan"
    )


class Ejecucion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una pasada del flujo, con lo que la disparó y cómo acabó."""

    __tablename__ = "ejecucion"
    __table_args__ = (
        Index("ix_automatizaciones_ejecucion_flujo", "automatizacion_id", "created_at"),
        {"schema": SCHEMA},
    )

    automatizacion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.automatizacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    estado: Mapped[EstadoEjecucion] = mapped_column(
        enum_column(EstadoEjecucion, "estado_ejecucion"),
        nullable=False,
        default=EstadoEjecucion.EN_CURSO,
    )
    #: Qué la disparó: el evento, el webhook o el reloj.
    disparador: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Los datos con los que arrancó. Se guardan para poder reproducirla y
    #: para entender por qué tomó la rama que tomó.
    entrada: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    automatizacion: Mapped[Automatizacion] = relationship(back_populates="ejecuciones")
    pasos: Mapped[list["PasoEjecucion"]] = relationship(
        back_populates="ejecucion", cascade="all, delete-orphan", lazy="selectin"
    )


class PasoEjecucion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Qué hizo cada nodo.

    Sin esto, un flujo de seis nodos que falla es una caja negra: se sabe que
    no funcionó y nada más. Guardando entrada y salida de cada paso se puede
    señalar el nodo exacto y ver con qué datos llegó.
    """

    __tablename__ = "paso_ejecucion"
    __table_args__ = ({"schema": SCHEMA},)

    ejecucion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ejecucion.id", ondelete="CASCADE"),
        nullable=False,
    )
    nodo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo_nodo: Mapped[str] = mapped_column(String(64), nullable=False)
    #: En qué orden se ejecutó. El grafo puede recorrerse de formas distintas
    #: según las ramas, así que el orden no se deduce de la definición.
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    estado: Mapped[EstadoPaso] = mapped_column(
        enum_column(EstadoPaso, "estado_paso"), nullable=False, default=EstadoPaso.OK
    )
    salida: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: Por qué salida se fue. En un nodo con ramas es lo que explica el resto
    #: de la ejecución.
    ruta: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duracion_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ejecucion: Mapped[Ejecucion] = relationship(back_populates="pasos")
