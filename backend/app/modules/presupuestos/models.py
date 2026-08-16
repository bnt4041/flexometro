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

from app.core.enums import OrigenDato, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "presupuestos"


class TipoConcepto(StrEnum):
    """Niveles de la cadena de Ramírez de Arellano que viven en el árbol.

    El precio de suministro no está aquí: vive en `catalogo` porque es el
    precio de un proveedor concreto, no un nodo del árbol de descomposición.
    Los tipos estructurales (capítulo, partida presupuestada) se añaden en
    Fase 3; por eso los enums se guardan como VARCHAR con CHECK y no como tipo
    nativo, para que sumar un valor sea una migración trivial.
    """

    BASICO = "basico"
    AUXILIAR = "auxiliar"
    UNITARIO = "unitario"


class NaturalezaConcepto(StrEnum):
    """Clasificación del recurso. Réplica del campo TIPO del registro ~C de
    FIEBDC-3, para que la importación de Fase 5 no tenga que inventar un mapeo."""

    SIN_CLASIFICAR = "sin_clasificar"
    MANO_OBRA = "mano_obra"
    MAQUINARIA = "maquinaria"
    MATERIAL = "material"
    RESIDUO = "residuo"
    OTRO = "otro"


class OrigenPrecio(StrEnum):
    """De dónde sale el precio del concepto. Es lo que gobierna la cascada.

    - MANUAL: lo teclea una persona y nadie lo pisa.
    - PRODUCTO: lo toma de la tarifa preferente del producto en el catálogo.
    - DESCOMPOSICION: se calcula sumando sus hijos. Es el caso de auxiliares y
      unitarios, y de cualquier básico que se descomponga.
    """

    MANUAL = "manual"
    PRODUCTO = "producto"
    DESCOMPOSICION = "descomposicion"


class Concepto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Nodo del árbol de precios.

    Una sola tabla para básicos, auxiliares y unitarios porque son el mismo
    objeto en distinto nivel del árbol: es exactamente como lo modela FIEBDC-3
    (registro ~C más registro ~D de descomposición), y es lo que permite que un
    auxiliar contenga otro auxiliar o que un unitario funcional agrupe
    unitarios sin casos especiales.
    """

    __tablename__ = "concepto"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="concepto_codigo_unique"),
        Index("ix_presupuestos_concepto_resumen", "organization_id", "resumen"),
        Index("ix_presupuestos_concepto_tipo", "organization_id", "tipo"),
        {"schema": SCHEMA},
    )

    # FIEBDC-3 usa el sufijo del código como convención: '#' final para
    # capítulos, '%' para auxiliares, '##' para la raíz de la obra.
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    tipo: Mapped[TipoConcepto] = mapped_column(
        enum_column(TipoConcepto, "tipo_concepto"), nullable=False
    )
    naturaleza: Mapped[NaturalezaConcepto] = mapped_column(
        enum_column(NaturalezaConcepto, "naturaleza_concepto"),
        nullable=False,
        default=NaturalezaConcepto.SIN_CLASIFICAR,
    )

    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    # Descripción larga: el registro ~T de FIEBDC-3.
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Precio unitario efectivo, ya redondeado a dos decimales según la
    # convención Presto. Es un valor materializado, no calculado al vuelo: un
    # presupuesto de miles de partidas no puede recalcular el árbol entero en
    # cada lectura.
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    origen_precio: Mapped[OrigenPrecio] = mapped_column(
        enum_column(OrigenPrecio, "origen_precio"),
        nullable=False,
        default=OrigenPrecio.MANUAL,
    )
    fecha_precio: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Enlace al catálogo cuando el precio viene de una tarifa de proveedor.
    producto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("catalogo.producto.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Porcentaje de costes indirectos, aplicado sobre el coste directo. Es
    # propio de los unitarios; en los básicos y auxiliares se deja a nulo.
    costes_indirectos: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )
    atributos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    lineas: Mapped[list["Descomposicion"]] = relationship(
        back_populates="padre",
        cascade="all, delete-orphan",
        foreign_keys="Descomposicion.padre_id",
        order_by="Descomposicion.orden",
    )


class Descomposicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del descompuesto: cuánto hijo lleva una unidad del padre.

    No hay unicidad sobre (padre, hijo) a propósito: FIEBDC-3 admite que un
    concepto aparezca más de una vez en la misma descomposición, y forzar la
    unicidad rompería la importación de bancos reales en Fase 5. El cálculo
    suma todas las líneas, así que el resultado es el mismo.
    """

    __tablename__ = "descomposicion"
    __table_args__ = (
        Index("ix_presupuestos_descomposicion_padre", "padre_id"),
        Index("ix_presupuestos_descomposicion_hijo", "hijo_id"),
        {"schema": SCHEMA},
    )

    padre_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="CASCADE"),
        nullable=False,
    )
    hijo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        # RESTRICT: borrar un concepto que alguien usa debe fallar, no vaciar
        # el descompuesto de otro en silencio.
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Cantidad de hijo por unidad de padre. Seis decimales: encadenar 1/3 con
    # dos decimales deforma el precio varios céntimos en tres niveles.
    rendimiento: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    # FIEBDC-3 separa FACTOR de RENDIMIENTO; el coste aportado es el producto
    # de ambos por el precio del hijo.
    factor: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("1")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    padre: Mapped[Concepto] = relationship(
        back_populates="lineas", foreign_keys=[padre_id]
    )
    hijo: Mapped[Concepto] = relationship(foreign_keys=[hijo_id])
