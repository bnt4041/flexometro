"""Quién quiere enterarse de qué, y por dónde.

Una suscripción es la unidad: «a este grupo, avísale de las obras paradas más
de 90 días, por campana y WhatsApp». Los canales y el plazo van EN la
suscripción, no en una regla aparte: dos grupos pueden querer el mismo aviso
por vías distintas, y con los canales fuera haría falta duplicar la regla
entera para conseguirlo.

Por eso tampoco hay una pantalla de reglas: esto se configura desde la ficha
de la persona o del grupo, que es donde estás cuando te haces la pregunta.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "notificaciones"


class SuscripcionAviso(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    __tablename__ = "suscripcion"
    __table_args__ = (
        # Una sola suscripción por destinatario y evento: dos filas iguales
        # con canales distintos harían que el mismo aviso llegara dos veces.
        UniqueConstraint(
            "organization_id", "tipo_evento", "usuario_subject", "grupo_id",
            name="suscripcion_unique",
        ),
        Index("ix_notificaciones_suscripcion_evento", "organization_id", "tipo_evento", "activa"),
        {"schema": SCHEMA},
    )

    #: Código del catálogo (`catalogo.py`). No es FK: los tipos de evento
    #: viven en el registro de código, igual que `module_code` en los permisos.
    tipo_evento: Mapped[str] = mapped_column(String(64), nullable=False)

    #: Uno de los dos, nunca los dos. Por grupo es lo normal —se mantiene solo
    #: cuando alguien entra o sale—; por persona, para las excepciones.
    usuario_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    grupo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("core.grupo.id", ondelete="CASCADE"), nullable=True
    )

    #: `["campana", "email", "whatsapp"]`. La campana no pasa por el puerto de
    #: mensajería (es una fila en la bandeja); las otras dos sí.
    canales: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: Los huecos del tipo de evento, ya rellenos: `{"dias": 90}`.
    parametros: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AvisoEmitido(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Lo que una vigilancia ya avisó, para no repetirlo cada hora.

    Sin esto, «esta obra lleva 90 días parada» se mandaría en cada pasada
    mientras siguiera parada. La gente aprende a ignorar un aviso así en una
    semana, y entonces deja de servir también para lo que sí importa.

    Va por suscripción y no por evento: si alguien se suscribe hoy, tiene que
    enterarse de lo que ya está pasando, no solo de lo que pase a partir de
    ahora.
    """

    __tablename__ = "aviso_emitido"
    __table_args__ = (
        UniqueConstraint("suscripcion_id", "clave", name="aviso_emitido_unique"),
        {"schema": SCHEMA},
    )

    suscripcion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.suscripcion.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: El registro concreto (el id de la obra, del documento…).
    clave: Mapped[str] = mapped_column(String(120), nullable=False)


class PreferenciaUsuario(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Lo poco que es de la persona y no de la suscripción.

    Qué avisos recibe y por dónde se decide en su ficha (`SuscripcionAviso`).
    Aquí solo queda su móvil —que hace falta para WhatsApp y no está en
    Keycloak— y el silencio temporal.
    """

    __tablename__ = "preferencia_usuario"
    __table_args__ = (
        UniqueConstraint("organization_id", "usuario_subject", name="preferencia_unique"),
        {"schema": SCHEMA},
    )

    usuario_subject: Mapped[str] = mapped_column(String(120), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: Silencio temporal, para vacaciones. La campana se sigue llenando: lo
    #: que se para es lo que interrumpe.
    silenciado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
