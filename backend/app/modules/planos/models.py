"""Biblioteca de planos: el fichero, sus hojas, sus capas y lo dibujado encima.

Dos decisiones que conviene entender antes de leer el resto.

**Las coordenadas se guardan en el espacio propio de la hoja**, no en píxeles
de pantalla ni normalizadas a 0-1. Es decir, en las unidades que tiene la
página a escala 1 (puntos PDF, o píxeles del bitmap). Así el dibujo sobrevive
a cualquier zoom y a cualquier tamaño de ventana, y la escala es un solo
número —`metros_por_unidad`— en vez de depender del ancho con el que se
pintó. Normalizar a 0-1 habría hecho que X e Y tuvieran escalas físicas
distintas en cuanto la hoja no fuese cuadrada.

**El valor de una medición lo calcula el servidor**, aunque el navegador lo
enseñe mientras se dibuja. El número que se guarda y el que acaba en una
partida no pueden depender de lo que diga el cliente.
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
from app.modules.planos.enums import OrigenPlano, TipoElemento

SCHEMA = "planos"


class Plano(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un documento de la biblioteca. El fichero original se guarda intacto en
    el almacén de objetos y nunca se sobreescribe: reescalar o anotar no toca
    el original, solo lo que cuelga de él."""

    __tablename__ = "plano"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="plano_codigo_unique"),
        Index("ix_planos_plano_obra", "organization_id", "obra_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Un plano puede colgar de una obra, de un presupuesto, de los dos o de
    # ninguno: la biblioteca sirve también para lo que todavía no es de nadie.
    obra_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("obras.obra.id", ondelete="SET NULL"), nullable=True
    )
    presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )

    origen: Mapped[OrigenPlano] = mapped_column(
        enum_column(OrigenPlano, "origen_plano"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hojas: Mapped[list["HojaPlano"]] = relationship(
        back_populates="plano", cascade="all, delete-orphan", order_by="HojaPlano.numero"
    )
    capas: Mapped[list["CapaPlano"]] = relationship(
        back_populates="plano", cascade="all, delete-orphan", order_by="CapaPlano.orden"
    )


class HojaPlano(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una página. Cada una se calibra por separado porque cada una puede venir
    a una escala distinta —un plano de situación y un detalle constructivo en el
    mismo PDF es lo normal."""

    __tablename__ = "hoja_plano"
    __table_args__ = (
        UniqueConstraint("plano_id", "numero", name="hoja_plano_numero_unique"),
        {"schema": SCHEMA},
    )

    plano_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.plano.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)

    #: Tamaño de la página a escala 1, en sus propias unidades. Es el sistema
    #: de coordenadas en el que se guarda todo lo dibujado.
    ancho: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    alto: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    #: Cuántos metros reales mide una unidad de la hoja. Nulo mientras no se
    #: haya calibrado, y entonces NADA se puede medir: es mejor no poder medir
    #: que dar un número inventado.
    metros_por_unidad: Mapped[Decimal | None] = mapped_column(Numeric(18, 9), nullable=True)

    #: Con qué se calibró, para poder revisarlo y repetirlo. Dos puntos en
    #: coordenadas de hoja y la distancia real que hay entre ellos.
    calibracion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: Los trazos del DXF, ya aplanados y en coordenadas de hoja. Es a la vez
    #: lo que se pinta y lo que se mide: pinchar una entidad da su longitud
    #: exacta, no una estimación sobre píxeles. Nulo en PDF e imagen, que no
    #: tienen geometría que leer.
    dibujo: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    plano: Mapped[Plano] = relationship(back_populates="hojas")
    elementos: Mapped[list["ElementoPlano"]] = relationship(
        back_populates="hoja", cascade="all, delete-orphan"
    )


class CapaPlano(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Las capas son del plano, no de la hoja: «Instalaciones» quiere decir lo
    mismo en la planta baja y en la primera, y tenerlas por hoja obligaría a
    recrearlas y a apagarlas una por una."""

    __tablename__ = "capa_plano"
    __table_args__ = ({"schema": SCHEMA},)

    plano_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.plano.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#b45309")
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Una capa bloqueada se ve pero no se toca. Evita mover sin querer el
    #: replanteo mientras se anota encima.
    bloqueada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    plano: Mapped[Plano] = relationship(back_populates="capas")


class ElementoPlano(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Cualquier cosa dibujada: una nota, una línea auxiliar o una medición."""

    __tablename__ = "elemento_plano"
    __table_args__ = (
        Index("ix_planos_elemento_hoja", "organization_id", "hoja_id"),
        {"schema": SCHEMA},
    )

    hoja_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.hoja_plano.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Nulo = capa por defecto. Se permite para que dibujar no obligue a crear
    #: capas antes de haber dibujado nada.
    capa_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{SCHEMA}.capa_plano.id", ondelete="SET NULL"),
        nullable=True,
    )
    tipo: Mapped[TipoElemento] = mapped_column(
        enum_column(TipoElemento, "tipo_elemento"), nullable=False
    )

    #: `[{"x": ..., "y": ...}, ...]` en coordenadas de hoja. Una nota tiene un
    #: punto; una longitud, dos o más; un área, tres o más.
    geometria: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)

    #: Lo que mide, ya en unidades reales. Lo calcula el servidor a partir de
    #: `geometria` y de la escala de la hoja; nulo en lo que no mide.
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unidad: Mapped[str | None] = mapped_column(String(10), nullable=True)

    #: A qué línea de medición dio lugar, si se llevó a una partida. Sirve para
    #: no aplicar dos veces lo mismo y para poder volver del presupuesto al
    #: sitio del plano de donde salió el número.
    linea_medicion_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    #: Lo dibujó la IA al revisar el plano, no una persona. Su geometría sale
    #: de mirar la imagen, así que es aproximada: se enseña marcada, se ajusta
    #: arrastrando, y nunca se lleva sola a una partida.
    propuesto_ia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    hoja: Mapped[HojaPlano] = relationship(back_populates="elementos")
