"""El universo Plexo: organizaciones que se dejan encontrar y se conectan
entre sí para colaborar — de cuentas distintas, empresas que no se conocían.

Es la primera vez que un dato cruza a propósito la frontera de organización
que RLS impone en el resto de la aplicación. Por eso las dos tablas de aquí
NO usan `OrganizationMixin`: `Perfil` vive en su propia organización pero
tiene que poder LEERSE desde otra (para buscarla), y `Vinculo` no pertenece a
una sola organización, pertenece a la pareja — ver la política RLS de la
migración para cómo se acota cada caso sin abrir más de lo necesario.

La pareja de organizaciones no se repite mientras haya una invitación viva
(pendiente o aceptada): eso lo impone una columna generada en Postgres
(`par_normalizado`, con `LEAST`/`GREATEST` para que A→B y B→A cuenten como la
misma pareja) que no hace falta mapear aquí — la aplicación nunca la lee, solo
existe para que la base la haga cumplir sola. Está en la migración.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.plexo.enums import EstadoVinculo

SCHEMA = "plexo"


class Perfil(TimestampMixin, Base):
    """Un interruptor por organización: «quiero que me puedan encontrar».

    `organization_id` es la clave primaria a propósito — hay como mucho un
    perfil por organización, y así no hace falta una columna `id` más.
    Apagado (`visible=False`) por defecto: nadie entra en el universo Plexo
    sin haberlo pedido.
    """

    __tablename__ = "perfil"
    __table_args__ = ({"schema": SCHEMA},)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.organization.id", ondelete="CASCADE"),
        primary_key=True,
    )
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Vinculo(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Una invitación a conectar, y lo que queda de ella si se acepta.

    No lleva `AutoriaMixin`: «quién lo creó» aquí es siempre alguien de la
    organización origen, y ponerlo en las mismas columnas que usa el resto de
    la aplicación (pensadas para "quién creó ESTE registro de MI
    organización") confundiría a quien lea el modelo. Van con nombre propio:
    `invitado_por_*` y `respondido_por_*`.
    """

    __tablename__ = "vinculo"
    __table_args__ = (
        Index("ix_plexo_vinculo_origen", "organizacion_origen_id"),
        Index("ix_plexo_vinculo_destino", "organizacion_destino_id"),
        {"schema": SCHEMA},
    )

    organizacion_origen_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.organization.id", ondelete="CASCADE"),
        nullable=False,
    )
    organizacion_destino_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("core.organization.id", ondelete="CASCADE"),
        nullable=False,
    )
    estado: Mapped[EstadoVinculo] = mapped_column(
        enum_column(EstadoVinculo, "estado_vinculo"),
        nullable=False,
        default=EstadoVinculo.PENDIENTE,
    )
    mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)

    invitado_por_subject: Mapped[str] = mapped_column(String(120), nullable=False)
    invitado_por_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    respondido_por_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    respondido_por_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    respondido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
