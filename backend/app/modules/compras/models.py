"""Albaranes de material: lo que entra en obra desde un proveedor, y
solicitudes de precios a proveedor (la "separata" que rellenan ellos).

`AlbaranLinea.capitulo_id` es opcional y es lo que permite que el informe de
coste real vs. presupuestado compare por capítulo y no solo en total — la
misma idea que `ParteTrabajo.capitulo_id` en el módulo `obras`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "compras"


class EstadoAlbaran(StrEnum):
    BORRADOR = "borrador"
    CONFORMADO = "conformado"
    FACTURADO = "facturado"


class Albaran(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un albarán de proveedor recibido en una obra."""

    __tablename__ = "albaran"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="albaran_codigo_unique"),
        Index("ix_compras_albaran_obra", "obra_id"),
        Index("ix_compras_albaran_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    # El número que trae el propio albarán del proveedor; no es el mismo
    # concepto que `codigo`, que es la referencia interna correlativa.
    numero_proveedor: Mapped[str | None] = mapped_column(String(60), nullable=True)

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("obras.obra.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )

    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[EstadoAlbaran] = mapped_column(
        enum_column(EstadoAlbaran, "estado_albaran"),
        nullable=False,
        default=EstadoAlbaran.BORRADOR,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    lineas: Mapped[list["AlbaranLinea"]] = relationship(
        back_populates="albaran",
        cascade="all, delete-orphan",
        order_by="AlbaranLinea.orden",
    )


class AlbaranLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del albarán: cantidad de un concepto a un precio.

    `concepto_id` es opcional, igual que en `Partida`: un material fuera del
    banco de precios (una compra puntual) se registra a mano con su
    descripción, sin forzar un alta solo para esta línea.
    """

    __tablename__ = "albaran_linea"
    __table_args__ = (
        Index("ix_compras_albaran_linea_albaran", "albaran_id"),
        Index("ix_compras_albaran_linea_capitulo", "capitulo_id"),
        {"schema": SCHEMA},
    )

    albaran_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.albaran.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )
    # SET NULL: igual que en ParteTrabajo, borrar el capítulo no borra el
    # coste ya incurrido, lo deja "sin asignar" en el informe.
    capitulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.capitulo.id", ondelete="SET NULL"),
        nullable=True,
    )

    descripcion: Mapped[str] = mapped_column(String(250), nullable=False)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    albaran: Mapped[Albaran] = relationship(back_populates="lineas")


# --- Solicitud de precios a proveedor (la "separata") ---


class EstadoSolicitud(StrEnum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    RESPONDIDA = "respondida"
    APROBADA = "aprobada"
    DESCARTADA = "descartada"
    CADUCADA = "caducada"


class SolicitudPrecios(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Petición de oferta a UN proveedor sobre una selección de partidas.

    Para comparar varias ofertas se hacen varias solicitudes sobre la misma
    selección; el comparativo del presupuesto las junta después.
    """

    __tablename__ = "solicitud_precios"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="solicitud_precios_codigo_unique"),
        Index("ix_compras_solicitud_precios_presupuesto", "presupuesto_id"),
        Index("ix_compras_solicitud_precios_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[EstadoSolicitud] = mapped_column(
        enum_column(EstadoSolicitud, "estado_solicitud"),
        nullable=False,
        default=EstadoSolicitud.BORRADOR,
    )

    fecha_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    respondida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    # El presupuesto-oferta que se genera cuando el proveedor cierra su
    # respuesta. La FK va en este sentido (compras -> presupuestos) a
    # propósito: es la dirección que ya tiene el grafo de dependencias entre
    # módulos, y ponerla al revés obligaría a invertirlo.
    oferta_presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Quién la envió. No basta con `creado_por_subject` de AutoriaMixin: es a
    # esta persona a quien hay que atribuir el presupuesto-oferta que llegue
    # (ver `publico_service`), porque atribuírselo al proveedor lo dejaría
    # invisible para quien tiene el permiso "solo los míos".
    emisor_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emisor_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)

    lineas: Mapped[list["SolicitudLinea"]] = relationship(
        back_populates="solicitud",
        cascade="all, delete-orphan",
        order_by="SolicitudLinea.orden",
    )


class SolicitudLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una partida de la separata: copia CONGELADA de la partida en el momento
    del envío, más lo que aporta el proveedor.

    La copia es deliberada: si el presupuesto se edita después de mandar la
    separata, lo que el proveedor está cotizando no puede cambiarle bajo los
    pies. `partida_id` queda solo como rastro para poder volcar la oferta.

    Sin `AutoriaMixin` a propósito: esto lo rellena el proveedor, que no es un
    usuario del sistema. Como consecuencia el listener de auditoría no mira
    esta tabla, así que el servicio graba un `AccionAuditoria.EVENTO` sobre la
    solicitud al guardar precios y al cerrar la respuesta.
    """

    __tablename__ = "solicitud_linea"
    __table_args__ = (
        Index("ix_compras_solicitud_linea_solicitud", "solicitud_id"),
        {"schema": SCHEMA},
    )

    solicitud_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_precios.id", ondelete="CASCADE"),
        nullable=False,
    )
    partida_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.partida.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Copia congelada de la partida.
    capitulo_resumen: Mapped[str | None] = mapped_column(String(250), nullable=True)
    codigo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    medicion: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=Decimal("0.000"))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Lo que aporta el proveedor.
    precio_ofertado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    observaciones_proveedor: Mapped[str | None] = mapped_column(Text, nullable=True)
    aprobada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    solicitud: Mapped[SolicitudPrecios] = relationship(back_populates="lineas")


class AccesoToken(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Resolución del enlace del proveedor: token -> organización.

    ⚠️ ES LA ÚNICA TABLA DE NEGOCIO DELIBERADAMENTE FUERA DE RLS. Tiene que
    serlo: el proveedor llega sin sesión, así que hay que averiguar a qué
    organización pertenece su enlace ANTES de que exista contexto y, sin
    contexto, cualquier tabla con RLS devuelve cero filas. Es exactamente el
    mismo problema —y la misma solución— que `core.organization`, que también
    está fuera de RLS para poder resolver a quién pertenece quien acaba de
    autenticarse (ver la migración `core_0002`).

    Por eso se queda en lo mínimo indispensable y OPACO: un hash y dos
    referencias. Todo el estado mutable del enlace (caducidad, revocación,
    contadores) vive en `AccesoEstado`, que SÍ tiene RLS y se lee ya dentro
    del contexto. Cuanto menos haya aquí, menos superficie hay que un
    endpoint autenticado pueda tocar por descuido saltándose el aislamiento.

    Nunca se guarda el token en claro: solo su SHA-256. El token viaja
    únicamente en el correo al proveedor.
    """

    __tablename__ = "acceso_token"
    __table_args__ = (
        UniqueConstraint("token_hash", name="acceso_token_hash_unique"),
        {"schema": SCHEMA},
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    solicitud_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_precios.id", ondelete="CASCADE"),
        nullable=False,
    )


class AccesoEstado(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Estado mutable del enlace del proveedor. Con RLS, a diferencia de
    `AccesoToken`: para cuando se lee esto la organización ya está fijada."""

    __tablename__ = "acceso_estado"
    __table_args__ = (
        UniqueConstraint("solicitud_id", name="acceso_estado_solicitud_unique"),
        {"schema": SCHEMA},
    )

    solicitud_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_precios.id", ondelete="CASCADE"),
        nullable=False,
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usos_ia: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ficheros_subidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_uso_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
