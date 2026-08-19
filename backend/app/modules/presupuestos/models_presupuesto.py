"""Estructura del presupuesto: obra, capítulos, partidas y mediciones.

Tablas propias, no tipos de `Concepto`. Una partida lleva datos que solo tienen
sentido dentro de su presupuesto —su medición, su sitio en un capítulo concreto
y el precio con el que se cerró—, así que el mismo unitario usado en dos obras
necesitaría dos filas de concepto. Sería llenar el cuadro de precios de
casi-duplicados, el mismo problema que evitamos separando `producto` de
`concepto`.
"""

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

from app.core.enums import OrigenDato, TipoIVA, enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "presupuestos"


class EstadoPresupuesto(StrEnum):
    BORRADOR = "borrador"
    EMITIDO = "emitido"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    CANCELADO = "cancelado"


class MetodoCalculo(StrEnum):
    """Cómo se pasa del coste al precio de venta — Fase 35.

    `CLASICO` es el encadenado español de toda la vida (PEM + %GG + %BI). Los
    otros dos son márgenes comerciales sobre el coste, y se diferencian en
    sobre qué se calcula el porcentaje: `INCREMENTO_SOBRE_COSTE` lo aplica al
    coste (markup: 100 € + 20 % = 120 €), mientras que `BENEFICIO_FINAL` lo
    entiende como porcentaje del precio de venta (margen: 100 € al 20 % son
    125 €, porque 25 es el 20 % de 125). Confundirlos es el error clásico al
    presupuestar, así que van explícitamente separados.
    """

    CLASICO = "clasico"
    INCREMENTO_SOBRE_COSTE = "incremento_sobre_coste"
    BENEFICIO_FINAL = "beneficio_final"


# Estados en los que el presupuesto deja de seguir al cuadro de precios.
ESTADOS_BLOQUEADOS = frozenset(
    {
        EstadoPresupuesto.EMITIDO,
        EstadoPresupuesto.APROBADO,
        EstadoPresupuesto.RECHAZADO,
        EstadoPresupuesto.CANCELADO,
    }
)


class Presupuesto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    __tablename__ = "presupuesto"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="presupuesto_codigo_unique"),
        Index("ix_presupuestos_presupuesto_estado", "organization_id", "estado"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Versiones ---
    # Las versiones de un mismo presupuesto se agrupan por `raiz_id`, que
    # apunta a la primera. En la primera es nulo: ella misma es la raíz.
    raiz_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # --- Plantillas ---
    # Una plantilla es un presupuesto como cualquier otro, marcado. Versionar e
    # instanciar una plantilla son la misma operación —copia profunda del
    # árbol—, así que no hacen falta tablas paralelas para lo mismo.
    es_plantilla: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Clasificación libre del tipo de obra ("rehabilitación de fachada",
    # "reforma integral"...). Es también la semilla del histórico sobre el que
    # trabajará la sugerencia de patrones por IA.
    tipo_obra: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    cliente_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    emplazamiento: Mapped[str | None] = mapped_column(String(250), nullable=True)

    fecha: Mapped[date | None] = mapped_column(Date, nullable=True)
    validez_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[EstadoPresupuesto] = mapped_column(
        enum_column(EstadoPresupuesto, "estado_presupuesto"),
        nullable=False,
        default=EstadoPresupuesto.BORRADOR,
    )

    # Porcentajes del encadenado PEM -> PEC. Los valores por defecto son los
    # habituales de la contratación pública española (RD 1098/2001): 13 % de
    # gastos generales y 6 % de beneficio industrial.
    gastos_generales: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("13.00")
    )
    beneficio_industrial: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("6.00")
    )
    tipo_iva: Mapped[TipoIVA] = mapped_column(
        enum_column(TipoIVA, "tipo_iva"), nullable=False, default=TipoIVA.GENERAL
    )
    # En obra subcontratada la factura va sin IVA y lo autorrepercute el
    # destinatario (art. 84.Uno.2.º f LIVA).
    inversion_sujeto_pasivo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Mientras está a false, las partidas siguen al cuadro de precios en
    # cascada. Se pone a true al salir de borrador: un presupuesto emitido no
    # puede moverse solo bajo los pies de quien lo firmó.
    precios_bloqueados: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Fase 35: cómo se calcula la venta a partir del coste. Por defecto el
    # modelo clásico, que es lo que hacía la aplicación hasta ahora.
    metodo_calculo: Mapped[MetodoCalculo] = mapped_column(
        enum_column(MetodoCalculo, "metodo_calculo"),
        nullable=False,
        default=MetodoCalculo.CLASICO,
    )
    # Porcentaje de los métodos no clásicos (el clásico usa gastos_generales y
    # beneficio_industrial, que ya existían).
    porcentaje_metodo: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )

    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    origen_dato: Mapped[OrigenDato] = mapped_column(
        enum_column(OrigenDato, "origen_dato"), nullable=False, default=OrigenDato.MANUAL
    )

    # Quién lleva el presupuesto — a diferencia de `creado_por_subject`
    # (`AutoriaMixin`, fijado una vez al crear), esto es reasignable en
    # cualquier momento. Mismo patrón subject+nombre desnormalizado que
    # `AutoriaMixin`: no hay FK a Keycloak, así que se guardan ambos para no
    # tener que resolverlo en cada lectura.
    responsable_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    responsable_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)

    capitulos: Mapped[list["Capitulo"]] = relationship(
        back_populates="presupuesto", cascade="all, delete-orphan"
    )


class Capitulo(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Nodo de la jerarquía del presupuesto. Profundidad libre."""

    __tablename__ = "capitulo"
    __table_args__ = (
        Index("ix_presupuestos_capitulo_presupuesto", "presupuesto_id"),
        Index("ix_presupuestos_capitulo_parent", "parent_id"),
        {"schema": SCHEMA},
    )

    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.presupuesto.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo.id", ondelete="CASCADE"),
        nullable=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    presupuesto: Mapped[Presupuesto] = relationship(back_populates="capitulos")
    partidas: Mapped[list["Partida"]] = relationship(
        back_populates="capitulo",
        cascade="all, delete-orphan",
        order_by="Partida.orden",
    )


class Partida(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea presupuestada: un precio unitario con su medición.

    `concepto_id` es opcional a propósito: una partida alzada no se descompone
    y lleva su precio a mano, y es algo corriente en un presupuesto real.
    """

    __tablename__ = "partida"
    __table_args__ = (
        Index("ix_presupuestos_partida_capitulo", "capitulo_id"),
        Index("ix_presupuestos_partida_presupuesto", "presupuesto_id"),
        Index("ix_presupuestos_partida_concepto", "concepto_id"),
        {"schema": SCHEMA},
    )

    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.presupuesto.id", ondelete="CASCADE"),
        nullable=False,
    )
    capitulo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        # SET NULL, no RESTRICT: borrar un unitario del cuadro no debe impedir
        # consultar un presupuesto ya cerrado; la partida conserva su copia.
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Copia de los datos del concepto en el momento de insertarlo. Es lo que
    # permite que un presupuesto emitido siga diciendo lo que decía.
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )

    # Solo se usa cuando la partida tiene descomposición propia (Fase 34): es
    # la copia del porcentaje que tenía el concepto al independizarse, para
    # que soltarse del banco no le cambie el precio por el camino.
    costes_indirectos: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # --- Venta (Fase 35) ---
    # `precio` es el COSTE unitario; esto es lo que se le cobra al cliente.
    # Se recalcula desde el coste según el método del presupuesto, salvo que
    # esté bloqueada: el candado es justamente para que un reajuste de
    # porcentajes no se lleve por delante un precio pactado a mano.
    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    venta_bloqueada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    importe_venta: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )

    # Materializados: cambian solo al tocar la medición o el precio.
    medicion: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    importe: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    capitulo: Mapped[Capitulo] = relationship(back_populates="partidas")
    lineas: Mapped[list["LineaMedicion"]] = relationship(
        back_populates="partida",
        cascade="all, delete-orphan",
        order_by="LineaMedicion.orden",
    )
    descomposicion: Mapped[list["PartidaDescomposicion"]] = relationship(
        back_populates="partida",
        cascade="all, delete-orphan",
        order_by="PartidaDescomposicion.orden",
    )


class PartidaDescomposicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Descompuesto propio de una partida — Fase 34.

    Por defecto una partida no tiene ninguno: hereda el del concepto del banco
    de precios, compartido con todos los presupuestos que lo usan. En cuanto
    se toca el precio de un componente "solo aquí", se clona el descompuesto
    del concepto a estas filas y la partida pasa a ser independiente: a partir
    de ese momento el banco puede cambiar sin arrastrarla.

    Cada línea congela código, descripción, unidad y precio del hijo por el
    mismo motivo que `Partida` los congela del concepto: un presupuesto
    entregado tiene que seguir diciendo lo que decía. `hijo_id` se guarda solo
    para poder rastrear de dónde salió, y por eso admite nulo (el concepto
    puede desaparecer del banco después).
    """

    __tablename__ = "partida_descomposicion"
    __table_args__ = (
        Index("ix_presupuestos_partida_descomposicion_partida", "partida_id"),
        Index("ix_presupuestos_partida_descomposicion_hijo", "hijo_id"),
        {"schema": SCHEMA},
    )

    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.partida.id", ondelete="CASCADE"),
        nullable=False,
    )
    hijo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    naturaleza: Mapped[str | None] = mapped_column(String(32), nullable=True)

    rendimiento: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    factor: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("1")
    )
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    partida: Mapped[Partida] = relationship(back_populates="descomposicion")


class FormulaMedicion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Fórmula reutilizable para medir — Fase 37.

    Por cuenta, no por organización, igual que el diccionario y las
    definiciones de campos libres: son vocabulario de trabajo compartido, no
    datos de negocio de una empresa concreta. Por eso no lleva RLS.

    La expresión la escribe el usuario y se evalúa con el analizador seguro de
    `formulas.py` — nunca con `eval()`.
    """

    __tablename__ = "formula_medicion"
    __table_args__ = (
        UniqueConstraint("cuenta_id", "nombre", name="formula_medicion_nombre_unique"),
        {"schema": SCHEMA},
    )

    cuenta_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("core.cuenta.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    expresion: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(250), nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LineaMedicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del estado de mediciones.

    Réplica del registro ~M de FIEBDC-3: comentario, unidades, longitud,
    anchura (latitud en la norma) y altura. El parcial es el producto de los
    que estén informados; los que no lo estén valen 1, no 0 — una línea con
    solo `uds = 5` mide 5, no 0.
    """

    __tablename__ = "linea_medicion"
    __table_args__ = (
        Index("ix_presupuestos_linea_medicion_partida", "partida_id"),
        {"schema": SCHEMA},
    )

    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.partida.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Fórmula (Fase 37) ---
    # Con fórmula, el parcial es `uds` por el resultado de la expresión, en vez
    # del producto de longitud/anchura/altura. `formula_expresion` es una copia
    # congelada: si alguien edita después la fórmula del catálogo, esta línea
    # sigue midiendo lo que medía, igual que la partida congela el precio del
    # concepto.
    formula_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.formula_medicion.id", ondelete="SET NULL"),
        nullable=True,
    )
    formula_expresion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    formula_valores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    comentario: Mapped[str | None] = mapped_column(String(250), nullable=True)
    uds: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    longitud: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    anchura: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    altura: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    parcial: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    partida: Mapped[Partida] = relationship(back_populates="lineas")
