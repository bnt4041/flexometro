"""Bancos y cajas de cada empresa (Fase 44).

Dónde está el dinero: una cuenta bancaria o una caja de efectivo. Va por
`organization_id` con RLS, no por cuenta como el diccionario o los patrones
de numeración — el dinero de una sociedad no es el de la otra, y un cobro
(que ya es de una organización concreta) nunca debe poder apuntar a la
cuenta de la empresa de al lado.

Distinto de `forma_pago`: esa dice CÓMO se cobró (transferencia, efectivo…),
esto dice DÓNDE entró o de dónde salió.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class TipoCuentaFinanciera(StrEnum):
    BANCO = "banco"
    CAJA = "caja"


class CuentaFinanciera(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "cuenta_financiera"
    __table_args__ = (
        UniqueConstraint("organization_id", "nombre", name="cuenta_financiera_nombre_unique"),
        Index("ix_core_cuenta_financiera_org", "organization_id", "activa"),
        {"schema": SCHEMA},
    )

    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[TipoCuentaFinanciera] = mapped_column(
        enum_column(TipoCuentaFinanciera, "tipo_cuenta_financiera"), nullable=False
    )
    # Solo tienen sentido en una cuenta de banco; una caja de efectivo los
    # deja vacíos. No se validan contra el IBAN real: es un dato de
    # referencia para imprimir en facturas y presupuestos, igual que el
    # `iban` de `Tercero`.
    banco: Mapped[str | None] = mapped_column(String(120), nullable=True)
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(11), nullable=True)
    # La que sale ya elegida al cobrar y la que se imprime en los documentos
    # si la plantilla no pide otra. Solo una por organización puede tenerlo
    # (lo garantiza el servicio, no un índice parcial: son dos o tres filas
    # por empresa y la corrección importa más aquí que el candado).
    es_predeterminada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
