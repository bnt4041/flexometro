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
    cuentas_bancarias: Mapped[list["CuentaBancariaTercero"]] = relationship(
        back_populates="tercero",
        cascade="all, delete-orphan",
        order_by="CuentaBancariaTercero.es_principal.desc()",
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

    # `selectin`: la razón social de la empresa hace falta en cuanto se
    # serializa un contacto (listado, ficha) — con carga perezosa reventaría
    # en async (`MissingGreenlet`), igual que `Cobro.cuenta_financiera`.
    tercero: Mapped[Tercero | None] = relationship(back_populates="contactos", lazy="selectin")

    @property
    def tercero_razon_social(self) -> str | None:
        return self.tercero.razon_social if self.tercero else None


class CuentaBancariaTercero(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Una cuenta bancaria que el tercero nos ha dado — a diferencia de
    `core.CuentaFinanciera` (Fase 44), que son las cuentas PROPIAS de la
    empresa. Puede haber varias por tercero: un proveedor a veces factura
    desde una cuenta y cobra por otra, y a un cliente domiciliado hay que
    guardarle el IBAN del que se le gira el recibo.

    Maestro compartido desde que nace (`activar_rls_maestro`, no
    `activar_rls`), igual que `Contacto`: si la cuenta está en
    `compartir_maestros`, el tercero es el mismo en sus dos empresas y sus
    cuentas bancarias también lo son — no tendría sentido que el mismo IBAN
    del mismo proveedor hubiera que darlo de alta dos veces."""

    __tablename__ = "cuenta_bancaria"
    __table_args__ = (
        Index("ix_terceros_cuenta_bancaria_tercero", "tercero_id"),
        {"schema": SCHEMA},
    )

    tercero_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.tercero.id", ondelete="CASCADE"),
        nullable=False,
    )
    titular: Mapped[str | None] = mapped_column(String(200), nullable=True)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    es_principal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tercero: Mapped[Tercero] = relationship(back_populates="cuentas_bancarias")


class EntidadContacto(StrEnum):
    """Qué tipo de registro puede llevar contactos asociados — Fase 28.
    Deliberadamente una lista corta y cerrada (no la reutiliza de
    `EntidadCampoLibre`, que es mucho más amplia): solo tiene sentido un
    interlocutor humano en los objetos "grandes" del negocio, no en sus
    líneas."""

    PRESUPUESTO = "presupuesto"
    OBRA = "obra"
    CERTIFICACION = "certificacion"
    FACTURA = "factura"


class ContactoAsociado(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Vínculo entre un `Contacto` y cualquier otro registro del negocio
    (presupuesto, obra, certificación, factura...) — Fase 28.

    `Contacto` no cambia: sigue siendo, opcionalmente, de un `Tercero`. Esto
    es una asociación aparte, N a N, para poder decir "esta persona está
    involucrada en este presupuesto" sin necesitar una columna nueva en cada
    tabla que quiera tener contactos — mismo motivo que `CampoLibreValor`
    guarda `entidad`/`entidad_id` sueltos en vez de una FK por tabla.
    """

    __tablename__ = "contacto_asociado"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "entidad", "entidad_id", "contacto_id",
            name="contacto_asociado_unique",
        ),
        Index("ix_terceros_contacto_asociado_entidad", "organization_id", "entidad", "entidad_id"),
        {"schema": SCHEMA},
    )

    entidad: Mapped[EntidadContacto] = mapped_column(
        enum_column(EntidadContacto, "entidad_contacto"), nullable=False
    )
    entidad_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    contacto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.contacto.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Libre, para matizar el porqué del vínculo ("decisor", "técnico de
    # obra"...) — no es un enum porque no hay un vocabulario cerrado que
    # tenga sentido igual en un presupuesto que en una factura.
    rol: Mapped[str | None] = mapped_column(String(80), nullable=True)

    contacto: Mapped[Contacto] = relationship()
