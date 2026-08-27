"""Ejecución de obra: la obra en sí, el personal propio y sus costes reales.

`Personal` son empleados de la organización, no terceros: un tercero
(cliente/proveedor/subcontratista) es una entidad externa, y la mano de obra
subcontratada ya se factura como compra a ese tercero. Personal es la plantilla
propia, la que genera coste de mano de obra día a día.

El patrón Asignación → ParteTrabajo replica a propósito el de Partida →
LineaMedicion: la asignación copia el coste/hora del trabajador en el momento
de asignarlo (igual que la partida copia el precio del concepto), así que subir
el coste/hora de alguien no reescribe el histórico de una obra ya cerrada; y el
parte de trabajo es a la asignación lo que la línea de medición es a la
partida, un registro día a día que se acumula en un coste materializado.
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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import enum_column
from app.core.models import AutoriaMixin, Base, OrganizationMixin, TimestampMixin, UUIDPrimaryKeyMixin

SCHEMA = "obras"


class EstadoObra(StrEnum):
    PLANIFICADA = "planificada"
    EN_EJECUCION = "en_ejecucion"
    PARALIZADA = "paralizada"
    FINALIZADA = "finalizada"
    CERRADA = "cerrada"


class TipoVinculo(StrEnum):
    """De dónde viene un presupuesto vinculado a la obra."""

    PRINCIPAL = "principal"
    # Lo que se contrata DESPUÉS de arrancar: una adenda al contrato, un
    # imprevisto, una ampliación. Se ve marcado como tal en el árbol de obra.
    ANEXO = "anexo"


class Obra(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """La ejecución real de uno o varios presupuestos.

    Un presupuesto describe una oferta; una obra es su ejecución en curso, con
    sus propias fechas y su propio estado.

    `presupuesto_id` apunta al PRINCIPAL, el que la originó — lo usan el
    informe de costes (`compras/costes.py`), el PEM del listado y las
    certificaciones. Ya no es la única vía: los demás presupuestos contratados
    después cuelgan de `ObraPresupuesto` como anexos. Por eso se le ha quitado
    el `UniqueConstraint` que había: la unicidad la lleva ahora la tabla de
    vínculos, que además admite varios.
    """

    __tablename__ = "obra"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="obra_codigo_unique"),
        Index("ix_obras_obra_estado", "organization_id", "estado"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(250), nullable=False)

    # RESTRICT: una obra en marcha no puede quedarse sin el presupuesto del
    # que saca su comparación de coste.
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    jefe_obra_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.personal.id", ondelete="SET NULL"),
        nullable=True,
    )

    estado: Mapped[EstadoObra] = mapped_column(
        enum_column(EstadoObra, "estado_obra"), nullable=False, default=EstadoObra.PLANIFICADA
    )
    fecha_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_fin_real: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    presupuestos: Mapped[list["ObraPresupuesto"]] = relationship(
        back_populates="obra",
        cascade="all, delete-orphan",
        order_by="ObraPresupuesto.orden",
    )


class ObraPresupuesto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Qué presupuestos se están ejecutando en esta obra.

    El principal es el que la originó; los anexos son lo que se contrata
    después (una adenda, un imprevisto, una ampliación). Al vincular uno se
    copia su árbol de capítulos y partidas al de la obra, marcando el origen —
    a partir de ahí la obra va por su cuenta y el presupuesto firmado con el
    cliente no se vuelve a tocar.
    """

    __tablename__ = "obra_presupuesto"
    __table_args__ = (
        UniqueConstraint("obra_id", "presupuesto_id", name="obra_presupuesto_unico"),
        Index("ix_obras_obra_presupuesto_obra", "obra_id"),
        {"schema": SCHEMA},
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT igual que en `Obra`: una obra en marcha no debe quedarse sin el
    # presupuesto contra el que compara.
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tipo: Mapped[TipoVinculo] = mapped_column(
        enum_column(TipoVinculo, "tipo_vinculo_obra"),
        nullable=False,
        default=TipoVinculo.ANEXO,
    )
    fecha_vinculacion: Mapped[date] = mapped_column(Date, nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    obra: Mapped[Obra] = relationship(back_populates="presupuestos")


class CapituloObra(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Nodo del árbol DE LA OBRA. Profundidad libre, como en presupuestos.

    Es una copia, no una vista: al vincular un presupuesto se duplica su árbol
    aquí y desde ese momento las dos cosas van por su cuenta. Es deliberado —
    el presupuesto es lo que se firmó con el cliente y no se toca nunca más,
    mientras que en obra la medición cambia cada semana. Compartir las mismas
    filas obligaría a elegir entre falsear el contrato o no poder medir.

    Lo que se paga por esa independencia es el rastro: `origen_presupuesto_id`
    y `origen_capitulo_id` dicen de dónde salió cada nodo, para poder comparar
    lo ejecutado contra lo contratado.
    """

    __tablename__ = "capitulo_obra"
    __table_args__ = (
        Index("ix_obras_capitulo_obra_obra", "obra_id"),
        Index("ix_obras_capitulo_obra_parent", "parent_id"),
        {"schema": SCHEMA},
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo_obra.id", ondelete="CASCADE"),
        nullable=True,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # SET NULL: si se borra el presupuesto de origen, la obra sigue en marcha;
    # lo único que se pierde es saber de dónde vino.
    origen_presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )
    origen_capitulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.capitulo.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Entró después de arrancar la obra: de un presupuesto anexo, o creado a
    # mano sobre la marcha. Es lo que hay que poder distinguir de un vistazo.
    es_anexo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    partidas: Mapped[list["PartidaObra"]] = relationship(
        back_populates="capitulo",
        cascade="all, delete-orphan",
        order_by="PartidaObra.orden",
    )


class PartidaObra(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea de la obra: lo que hay que ejecutar, con su medición real.

    A diferencia de la partida de presupuesto, esta **no lleva descompuesto**:
    en obra el coste real no sale de un descompuesto teórico, sale de los
    albaranes y de los partes de trabajo, que es lo que ya cruza
    `compras/costes.py`. Sí conserva coste y venta unitarios, porque el coste
    es la referencia contra la que se compara y la venta es lo que se
    certifica.
    """

    __tablename__ = "partida_obra"
    __table_args__ = (
        Index("ix_obras_partida_obra_obra", "obra_id"),
        Index("ix_obras_partida_obra_capitulo", "capitulo_id"),
        {"schema": SCHEMA},
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    capitulo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.capitulo_obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")

    # Coste unitario previsto y precio de venta al cliente, copiados del
    # presupuesto en el momento de vincularlo.
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )

    # Materializados, igual que en presupuestos: cambian solo al tocar la
    # medición o el precio.
    medicion: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    importe: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )
    importe_venta: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), nullable=False, default=Decimal("0.00")
    )

    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    origen_presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )
    origen_partida_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.partida.id", ondelete="SET NULL"),
        nullable=True,
    )
    es_anexo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    capitulo: Mapped[CapituloObra] = relationship(back_populates="partidas")
    lineas: Mapped[list["MedicionObra"]] = relationship(
        back_populates="partida",
        cascade="all, delete-orphan",
        order_by="MedicionObra.orden",
    )


class MedicionObra(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Un parcial de la medición real de una partida de obra.

    Calcado de `LineaMedicion` de presupuestos y con el mismo cálculo
    (`parcial_de`): las dimensiones no informadas valen 1, no 0. Se queda sin
    fórmulas a propósito — en obra se mide lo que hay, y la fórmula es una
    herramienta de la fase de presupuestar.
    """

    __tablename__ = "medicion_obra"
    __table_args__ = (
        Index("ix_obras_medicion_obra_partida", "partida_id"),
        {"schema": SCHEMA},
    )

    partida_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.partida_obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    comentario: Mapped[str | None] = mapped_column(String(250), nullable=True)
    uds: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    longitud: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    anchura: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    altura: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    parcial: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0.000")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # De qué parcial del presupuesto salió, o NULL si se midió en obra.
    #
    # Es lo que permite saber si desvincular un anexo tiraría trabajo real. No
    # sirve comparar `created_at` con el de la partida: `now()` en Postgres es
    # la hora de la TRANSACCIÓN, así que la copia y una medición hecha en la
    # misma petición llevan el mismo sello y salen iguales.
    origen_linea_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.linea_medicion.id", ondelete="SET NULL"),
        nullable=True,
    )

    partida: Mapped[PartidaObra] = relationship(back_populates="lineas")


class EstadoTarea(StrEnum):
    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    HECHA = "hecha"


class PrioridadTarea(StrEnum):
    BAJA = "baja"
    NORMAL = "normal"
    ALTA = "alta"


class Tarea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Algo que hay que hacer en una obra.

    El responsable es `Personal`, no un usuario de Keycloak: en obra se asigna
    al encargado o al oficial que está allí, y ese es alguien de la plantilla
    aunque no tenga cuenta en la aplicación. SET NULL para que dar de baja a un
    trabajador no borre la tarea — lo que se pierde es a quién estaba asignada.

    `orden` es la posición dentro de SU columna del tablero, no dentro de la
    obra: al arrastrar una tarjeta cambian el estado y el orden a la vez.
    """

    __tablename__ = "tarea"
    __table_args__ = (
        Index("ix_obras_tarea_obra", "obra_id"),
        Index("ix_obras_tarea_estado", "obra_id", "estado"),
        {"schema": SCHEMA},
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(250), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.personal.id", ondelete="SET NULL"),
        nullable=True,
    )
    fecha_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoTarea] = mapped_column(
        enum_column(EstadoTarea, "estado_tarea"),
        nullable=False,
        default=EstadoTarea.PENDIENTE,
    )
    prioridad: Mapped[PrioridadTarea] = mapped_column(
        enum_column(PrioridadTarea, "prioridad_tarea"),
        nullable=False,
        default=PrioridadTarea.NORMAL,
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cuándo se marcó hecha. Se pone y se quita al mover la tarjeta: sin esto
    # no se puede decir qué se cerró esta semana.
    completada_en: Mapped[date | None] = mapped_column(Date, nullable=True)


class Personal(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un trabajador propio de la organización."""

    __tablename__ = "personal"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="personal_codigo_unique"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    apellidos: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Texto libre a propósito: "oficial 1a", "peón", "encargado"... no hace
    # falta un catálogo cerrado para una plantilla propia.
    categoria: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Coste para la empresa (no lo que se le paga en mano): salario más
    # cargas sociales prorrateadas por hora. Es el valor por defecto que se
    # copia al asignarlo a una obra.
    coste_hora: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class Asignacion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Que un trabajador está adscrito a una obra, con su coste congelado.

    `coste_hora` se copia de `Personal` al crear la asignación: es la misma
    razón por la que una `Partida` copia el precio del `Concepto` — que subir
    el coste de alguien no reescriba en silencio el coste histórico de una
    obra que ya se cerró.
    """

    __tablename__ = "asignacion"
    __table_args__ = (
        Index("ix_obras_asignacion_obra", "obra_id"),
        Index("ix_obras_asignacion_personal", "personal_id"),
        {"schema": SCHEMA},
    )

    obra_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.obra.id", ondelete="CASCADE"),
        nullable=False,
    )
    personal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.personal.id", ondelete="RESTRICT"),
        nullable=False,
    )
    coste_hora: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    partes: Mapped[list["ParteTrabajo"]] = relationship(
        back_populates="asignacion",
        cascade="all, delete-orphan",
        order_by="ParteTrabajo.fecha",
    )


class ParteTrabajo(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Parte diario: horas reales de un trabajador en un día concreto.

    `coste` es `horas x coste_hora`, materializado en la fila para no
    recalcularlo en cada lectura del informe de coste real. `capitulo_id` es
    opcional: permite atribuir la mano de obra de ese día a un capítulo
    concreto del presupuesto de la obra, para que el informe compare por
    capítulo y no solo en total.
    """

    __tablename__ = "parte_trabajo"
    __table_args__ = (
        UniqueConstraint(
            "asignacion_id", "fecha", name="parte_trabajo_asignacion_fecha_unique"
        ),
        Index("ix_obras_parte_trabajo_asignacion", "asignacion_id"),
        Index("ix_obras_parte_trabajo_capitulo", "capitulo_id"),
        {"schema": SCHEMA},
    )

    asignacion_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.asignacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SET NULL: si se borra el capítulo, el coste ya incurrido no desaparece,
    # pasa a "sin asignar" en el informe.
    capitulo_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.capitulo.id", ondelete="SET NULL"),
        nullable=True,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    horas: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    coste: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    asignacion: Mapped[Asignacion] = relationship(back_populates="partes")
