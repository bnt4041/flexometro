"""Monedas y tipo de cambio (Fase 23) — a nivel de plataforma, no de cuenta:
el cambio EUR/USD de hoy es el mismo para todo el mundo, no algo que cada
tenant deba mantener por separado. Mismo nivel que `Cuenta`/`Organization`
(sin RLS, ver `app/core/rls.py`), solo que compartido por toda la
instalación en vez de por cuenta.

Solo de referencia por ahora (Fase 23): ningún presupuesto ni factura se
emite todavía en otra moneda — la app sigue siendo 100% EUR para los
documentos fiscales reales. `unidades_por_euro` es cuántas unidades de esta
moneda equivalen a 1 EUR (la misma convención con la que el BCE publica sus
tipos, "1 EUR = 1,08 USD"), para no tener que invertir la fracción al leer
la respuesta de la API de cambio.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "core"


class Moneda(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "moneda"
    __table_args__ = ({"schema": SCHEMA},)

    codigo: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    simbolo: Mapped[str] = mapped_column(String(5), nullable=False)
    # `None` hasta el primer refresco — EUR no necesita nunca (siempre 1).
    unidades_por_euro: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
