import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
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

from app.core.enums import OrigenDato, TipoPersona, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "terceros"


class FormaPago(StrEnum):
    TRANSFERENCIA = "transferencia"
    DOMICILIADO = "domiciliado"
    PAGARE = "pagare"
    CONFIRMING = "confirming"
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"


class Tercero(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Cliente, proveedor y/o subcontratista.

    Una sola ficha con roles en lugar de tablas separadas: en construcción es
    corriente que la misma empresa te suministre material y te contrate una
    obra, y duplicar los datos fiscales es garantía de descuadre.
    """

    __tablename__ = "tercero"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="tercero_codigo_unique"),
        UniqueConstraint("organization_id", "nif", name="tercero_nif_unique"),
        Index("ix_terceros_tercero_razon_social", "organization_id", "razon_social"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nif: Mapped[str | None] = mapped_column(String(20), nullable=True)
    razon_social: Mapped[str] = mapped_column(String(200), nullable=False)
    nombre_comercial: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_persona: Mapped[TipoPersona] = mapped_column(
        enum_column(TipoPersona, "tipo_persona"),
        nullable=False,
        default=TipoPersona.JURIDICA,
    )
    # Fase 20: clave del diccionario `forma_juridica` (S.L., S.A., Autónomo...)
    # — a diferencia de `forma_pago`/`pais`, no hay ningún enum de código
    # detrás: es una referencia libre a `core.entrada_diccionario`.
    forma_juridica: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Roles. No son excluyentes.
    es_cliente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    es_proveedor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    es_subcontratista: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    web: Mapped[str | None] = mapped_column(String(200), nullable=True)

    direccion: Mapped[str | None] = mapped_column(String(250), nullable=True)
    codigo_postal: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provincia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pais: Mapped[str] = mapped_column(String(2), nullable=False, default="ES")

    # Condiciones de pago y cobro.
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    forma_pago: Mapped[FormaPago | None] = mapped_column(
        enum_column(FormaPago, "forma_pago"), nullable=True
    )
    dias_pago: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Particularidades fiscales del sector en España.
    # Retención de IRPF aplicable a personas físicas / autónomos.
    irpf_retencion: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # Inversión del sujeto pasivo (art. 84.Uno.2º.f LIVA): en ejecución de obra
    # subcontratada la factura va sin IVA y lo autorrepercute el destinatario.
    inversion_sujeto_pasivo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Registro de Empresas Acreditadas (Ley 32/2006): obligatorio para
    # subcontratar en construcción, y caduca.
    rea_numero: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rea_caducidad: Mapped[date | None] = mapped_column(Date, nullable=True)

    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )
    datos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    contactos: Mapped[list["Contacto"]] = relationship(
        back_populates="tercero",
        cascade="all, delete-orphan",
        order_by="Contacto.nombre",
    )


class Contacto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Persona. Puede colgar de un tercero o existir por su cuenta (un
    arquitecto, un jefe de obra de la propiedad, un contacto suelto)."""

    __tablename__ = "contacto"
    __table_args__ = (
        Index("ix_terceros_contacto_nombre", "organization_id", "nombre"),
        {"schema": SCHEMA},
    )

    tercero_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.tercero.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Fase 20: clave del diccionario `tratamiento` (Sr., Sra., Don, Doña...).
    tratamiento: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    movil: Mapped[str | None] = mapped_column(String(30), nullable=True)
    es_principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tercero: Mapped[Tercero | None] = relationship(back_populates="contactos")
