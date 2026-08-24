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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OrigenDato, TipoIVA, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "presupuestos"


class Familia(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Clasificación arbórea del banco de precios. Jerarquía libre por autorreferencia.

    Venía del catálogo (Fase 2); se muda aquí al fusionarse `Producto` en
    `Concepto` (Fase 25): ya no tiene sentido un schema `catalogo` con una
    única tabla de clasificación.
    """

    __tablename__ = "familia"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="familia_codigo_unique"),
        {"schema": SCHEMA},
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.familia.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hijos: Mapped[list["Familia"]] = relationship(
        back_populates="padre", cascade="save-update"
    )
    padre: Mapped["Familia | None"] = relationship(
        back_populates="hijos", remote_side="Familia.id"
    )


class CapituloBanco(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Capítulo del banco de precios (Fase 50) — cómo se ORGANIZA el banco,
    en árbol, igual que los capítulos de un presupuesto.

    Deliberadamente distinto de `Familia`, aunque las dos sean jerárquicas:
    el capítulo dice DÓNDE está la ficha dentro del banco (una sola, y se
    mueve arrastrando), mientras que la familia sigue siendo una etiqueta de
    clasificación —qué ES la ficha— que se asigna aparte y en masa. Una
    ficha de hormigón puede vivir en el capítulo "Estructura" y llevar la
    familia "Material" sin que una cosa implique la otra.

    No se reutiliza `Capitulo` (el de presupuesto) porque aquel cuelga
    obligatoriamente de un `presupuesto_id`: son árboles distintos con
    ciclos de vida distintos.
    """

    __tablename__ = "capitulo_banco"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="capitulo_banco_codigo_unique"),
        Index("ix_presupuestos_capitulo_banco_padre", "organization_id", "parent_id"),
        {"schema": SCHEMA},
    )

    # RESTRICT como en `Familia`: borrar un capítulo con subcapítulos dentro
    # sería perder la rama entera sin avisar.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo_banco.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    # Descripción ampliada, en HTML — el mismo editor enriquecido que usan
    # los capítulos de presupuesto.
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    hijos: Mapped[list["CapituloBanco"]] = relationship(
        back_populates="padre", cascade="save-update"
    )
    padre: Mapped["CapituloBanco | None"] = relationship(
        back_populates="hijos", remote_side="CapituloBanco.id"
    )


class TipoConcepto(StrEnum):
    """Niveles de la cadena de Ramírez de Arellano que viven en el árbol.

    El precio de suministro es de un proveedor concreto, no un nodo del árbol
    de descomposición; vive en `PrecioSuministro`, aparte. Los tipos
    estructurales (capítulo, partida presupuestada) se añaden en Fase 3; por
    eso los enums se guardan como VARCHAR con CHECK y no como tipo nativo,
    para que sumar un valor sea una migración trivial.
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
    SERVICIO = "servicio"
    RESIDUO = "residuo"
    OTRO = "otro"


class OrigenPrecio(StrEnum):
    """De dónde sale el precio del concepto. Es lo que gobierna la cascada.

    - MANUAL: lo teclea una persona y nadie lo pisa.
    - PRODUCTO: lo toma de la tarifa preferente de su propio `PrecioSuministro`.
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

    # Porcentaje de costes indirectos, aplicado sobre el coste directo. Es
    # propio de los unitarios; en los básicos y auxiliares se deja a nulo.
    costes_indirectos: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # --- Banco de precios (Fase 25) ---
    # Estos cuatro campos venían de `catalogo.Producto`, fusionado aquí: un
    # concepto ya no necesita una fila aparte en otra tabla para tener EAN,
    # familia o precio de venta al cliente. `precio` (arriba) sigue siendo el
    # de coste, el que alimenta la cascada; `precio_venta` es comercial y
    # nadie lo toca automáticamente.
    ean: Mapped[str | None] = mapped_column(String(14), nullable=True)
    familia_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.familia.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Dónde vive la ficha dentro del árbol del banco (Fase 50) — distinto de
    # `familia_id`, que es su clasificación. SET NULL: borrar un capítulo
    # deja sus fichas sueltas en la raíz, nunca las borra.
    capitulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo_banco.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Posición dentro de su capítulo. Antes el banco se ordenaba solo por
    # `tipo, codigo`; con la rejilla hace falta un orden que el usuario pueda
    # cambiar arrastrando.
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    precio_venta: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tipo_iva: Mapped[TipoIVA] = mapped_column(
        enum_column(TipoIVA, "tipo_iva"), nullable=False, default=TipoIVA.GENERAL
    )

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )
    atributos: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    familia: Mapped[Familia | None] = relationship()
    lineas: Mapped[list["Descomposicion"]] = relationship(
        back_populates="padre",
        cascade="all, delete-orphan",
        foreign_keys="Descomposicion.padre_id",
        order_by="Descomposicion.orden",
    )
    suministros: Mapped[list["PrecioSuministro"]] = relationship(
        back_populates="concepto",
        cascade="all, delete-orphan",
        order_by="PrecioSuministro.vigente_desde.desc()",
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


class PrecioSuministro(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Precio de un concepto puesto por un proveedor concreto en una fecha.

    Primer eslabón de la cadena de Ramírez de Arellano. Cuatro decimales a
    propósito: las tarifas de proveedor llegan así (material a granel,
    tornillería), y el redondeo a dos decimales de la convención Presto se
    aplica al encadenar conceptos, a partir del precio básico. Redondear aquí
    metería error antes de empezar.

    Venía de `catalogo.Producto` (Fase 2); se muda aquí al fusionarse en
    `Concepto` (Fase 25): un básico con `origen_precio=PRODUCTO` tiene ahora
    sus propias tarifas directamente, sin una tabla `producto` intermedia.
    """

    __tablename__ = "precio_suministro"
    __table_args__ = (
        Index("ix_presupuestos_precio_suministro_concepto", "organization_id", "concepto_id"),
        Index("ix_presupuestos_precio_suministro_proveedor", "organization_id", "proveedor_id"),
        # Como mucho una tarifa preferente por concepto.
        Index(
            "uq_presupuestos_precio_suministro_preferente",
            "concepto_id",
            unique=True,
            postgresql_where=text("es_preferente"),
        ),
        {"schema": SCHEMA},
    )

    concepto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="CASCADE"),
        nullable=False,
    )
    # FK entre schemas: es la dependencia presupuestos -> terceros hecha
    # explícita en la base de datos, no solo en el registro de módulos.
    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )

    precio: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    descuento: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0")
    )
    cantidad_minima: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    plazo_entrega_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referencia_proveedor: Mapped[str | None] = mapped_column(String(60), nullable=True)

    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    es_preferente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    concepto: Mapped[Concepto] = relationship(back_populates="suministros")

    @property
    def precio_neto(self) -> Decimal:
        """Precio con el descuento de tarifa aplicado, sin redondear a dos."""
        return (self.precio * (Decimal("100") - self.descuento) / Decimal("100")).quantize(
            Decimal("0.0001")
        )


class HistoricoPrecioConcepto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Rastro de cada precio que ha tenido un concepto.

    `recalcular_cascada` añade una fila aquí cada vez que el precio
    materializado de un concepto cambia de verdad — no en cada recálculo, que
    corre en cascada sobre todo lo que depende de un cambio y la mayoría de las
    veces no mueve el precio de un nodo concreto. Es lo único que permite
    responder "qué costes ha tenido" en la ficha del banco de precios: antes
    de esta tabla, cada recálculo pisaba el precio anterior sin dejar rastro.
    """

    __tablename__ = "historico_precio_concepto"
    __table_args__ = (
        Index(
            "ix_presupuestos_historico_precio_concepto_concepto",
            "organization_id", "concepto_id", "fecha",
        ),
        {"schema": SCHEMA},
    )

    concepto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="CASCADE"),
        nullable=False,
    )
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    origen_precio: Mapped[OrigenPrecio] = mapped_column(
        enum_column(OrigenPrecio, "origen_precio"), nullable=False
    )
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
