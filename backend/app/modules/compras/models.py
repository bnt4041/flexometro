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

from app.core.enums import TipoIVA, enum_column
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
        Index("ix_compras_albaran_pedido", "pedido_id"),
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
    # De qué pedido viene esta entrega — opcional: un albarán se puede seguir
    # dando de alta directo, sin pedido de por medio, igual que hasta ahora.
    # SET NULL: borrar el pedido no borra la entrega ya recibida en obra.
    pedido_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.pedido.id", ondelete="SET NULL"),
        nullable=True,
    )

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


# --- Pedidos a proveedor (orden de compra en firme) ---


class EstadoPedido(StrEnum):
    PENDIENTE = "pendiente"
    CONFIRMADO = "confirmado"
    SERVIDO_PARCIAL = "servido_parcial"
    SERVIDO = "servido"
    CANCELADO = "cancelado"


class Pedido(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Una orden de compra en firme a un proveedor.

    Distinto de `SolicitudPrecios` (que es solo pedir precio, comparar
    ofertas) y de `Albaran` (que es lo que entra físicamente en obra): el
    pedido es el paso intermedio, "esto es lo que se le encarga", tanto si
    viene de confirmar la oferta ganadora de una solicitud (`origen_*`
    rellenos) como si se hace directo a un proveedor conocido (ambos NULL).
    """

    __tablename__ = "pedido"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="pedido_codigo_unique"),
        Index("ix_compras_pedido_obra", "obra_id"),
        Index("ix_compras_pedido_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
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
    # De qué solicitud de precios / oferta ganadora viene, si viene de ahí —
    # SET NULL: borrar la solicitud o la oferta no borra el pedido ya hecho,
    # solo pierde el rastro de dónde salió.
    origen_solicitud_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_precios.id", ondelete="SET NULL"),
        nullable=True,
    )
    origen_oferta_presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )

    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_entrega_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoPedido] = mapped_column(
        enum_column(EstadoPedido, "estado_pedido"),
        nullable=False,
        default=EstadoPedido.PENDIENTE,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    lineas: Mapped[list["PedidoLinea"]] = relationship(
        back_populates="pedido",
        cascade="all, delete-orphan",
        order_by="PedidoLinea.orden",
    )


class PedidoLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del pedido — mismo esquema que `AlbaranLinea`: cantidad de
    un concepto (o de un material fuera de banco) a un precio."""

    __tablename__ = "pedido_linea"
    __table_args__ = (
        Index("ix_compras_pedido_linea_pedido", "pedido_id"),
        {"schema": SCHEMA},
    )

    pedido_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.pedido.id", ondelete="CASCADE"),
        nullable=False,
    )
    concepto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    descripcion: Mapped[str] = mapped_column(String(250), nullable=False)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    importe: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    pedido: Mapped[Pedido] = relationship(back_populates="lineas")


# --- Facturas de proveedor ---


class EstadoFacturaRecibida(StrEnum):
    PENDIENTE = "pendiente"
    PAGADA = "pagada"


class FacturaRecibida(
    UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base
):
    """Una factura que nos manda un proveedor, imputada a una obra.

    **No la emitimos nosotros**, así que no lleva serie ni numeración legal: lo
    que la identifica de cara al proveedor es SU número (`numero_proveedor`).
    `codigo` es solo la referencia interna correlativa, igual que en `Albaran`.
    Por eso tampoco hay `notificado_n8n_en` ni nada del circuito Veri*Factu —
    ese es un deber del que emite.

    `total` se guarda materializado en vez de recalcularse al leer: es el dato
    que viene en el papel, y si el proveedor lo redondea de otra forma manda el
    suyo, no nuestra aritmética.
    """

    __tablename__ = "factura_recibida"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "codigo", name="factura_recibida_codigo_unique"
        ),
        # El mismo proveedor no puede mandar dos veces la misma factura. Pillarlo
        # aquí evita pagar dos veces por un registro duplicado a mano.
        UniqueConstraint(
            "organization_id",
            "proveedor_id",
            "numero_proveedor",
            name="factura_recibida_numero_proveedor_unique",
        ),
        Index("ix_compras_factura_recibida_obra", "obra_id"),
        Index("ix_compras_factura_recibida_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    # El número que trae la factura del proveedor. Obligatorio, al contrario
    # que en el albarán: sin él no se puede reclamar ni cuadrar nada.
    numero_proveedor: Mapped[str] = mapped_column(String(60), nullable=False)

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
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    base_imponible: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tipo_iva: Mapped[TipoIVA] = mapped_column(
        enum_column(TipoIVA, "tipo_iva"), nullable=False, default=TipoIVA.GENERAL
    )
    # Obra subcontratada: la factura llega sin IVA y lo autorrepercutimos
    # nosotros (art. 84.Uno.2.º f LIVA). Es corriente en subcontratación.
    inversion_sujeto_pasivo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    cuota_iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    estado: Mapped[EstadoFacturaRecibida] = mapped_column(
        enum_column(EstadoFacturaRecibida, "estado_factura_recibida"),
        nullable=False,
        default=EstadoFacturaRecibida.PENDIENTE,
    )
    fecha_pago: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    albaranes: Mapped[list["FacturaRecibidaAlbaran"]] = relationship(
        back_populates="factura",
        cascade="all, delete-orphan",
    )


class FacturaRecibidaAlbaran(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Qué albaranes cubre una factura recibida.

    Es lo que permite cuadrar lo recibido con lo facturado: material que entró
    en obra y todavía nadie ha facturado, o una factura que no se corresponde
    con ninguna entrega. Una factura puede cubrir varios albaranes (lo normal
    en una mensual) y se deja que un albarán aparezca en varias, porque una
    entrega grande se factura a veces en partes.
    """

    __tablename__ = "factura_recibida_albaran"
    __table_args__ = (
        UniqueConstraint(
            "factura_id", "albaran_id", name="factura_recibida_albaran_unico"
        ),
        Index("ix_compras_factura_recibida_albaran_factura", "factura_id"),
        Index("ix_compras_factura_recibida_albaran_albaran", "albaran_id"),
        {"schema": SCHEMA},
    )

    factura_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.factura_recibida.id", ondelete="CASCADE"),
        nullable=False,
    )
    # CASCADE también aquí: si se borra el albarán, lo que desaparece es el
    # vínculo, no la factura — que sigue existiendo y habiendo que pagarla.
    albaran_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.albaran.id", ondelete="CASCADE"),
        nullable=False,
    )

    factura: Mapped[FacturaRecibida] = relationship(back_populates="albaranes")


# --- Solicitud de precios a proveedor (la "separata") ---


class EstadoSolicitud(StrEnum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    RESPONDIDA = "respondida"
    APROBADA = "aprobada"
    DESCARTADA = "descartada"
    CADUCADA = "caducada"


class SolicitudPrecios(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un paquete de trabajo con nombre ("Yeserías") sobre el que se pide
    precio: QUÉ se pide, una sola vez y común a todos.

    A quién se le pide vive en `SolicitudDestinatario` (uno por proveedor) y
    lo que cada uno oferta, en `OfertaLinea`. El desdoblamiento es lo que
    permite comparar de verdad: todos los proveedores cotizan exactamente la
    misma lista, en vez de N solicitudes paralelas que coinciden por
    casualidad.

    Las líneas son editables SIEMPRE, también después de enviar (decisión
    explícita del usuario): quien envía decide si reenvía a los proveedores
    anteriores, y se acepta que el comparativo tenga huecos donde alguien no
    haya cotizado algo.
    """

    __tablename__ = "solicitud_precios"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="solicitud_precios_codigo_unique"),
        Index("ix_compras_solicitud_precios_presupuesto", "presupuesto_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    # Cómo lo llama el usuario: "Yeserías", "Instalación eléctrica"…
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    presupuesto_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Del paquete: `borrador` mientras no haya salido a nadie, `enviada` en
    # cuanto sale al primero. El estado que de verdad manda es el de cada
    # destinatario, que va a su ritmo.
    estado: Mapped[EstadoSolicitud] = mapped_column(
        enum_column(EstadoSolicitud, "estado_solicitud"),
        nullable=False,
        default=EstadoSolicitud.BORRADOR,
    )

    fecha_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Quién lo creó. No basta con `creado_por_subject` de AutoriaMixin: es a
    # esta persona a quien hay que atribuir los presupuestos-oferta que
    # lleguen, porque atribuírselos al proveedor los dejaría invisibles para
    # quien tiene el permiso "solo los míos".
    emisor_subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emisor_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)

    lineas: Mapped[list["SolicitudLinea"]] = relationship(
        back_populates="solicitud",
        cascade="all, delete-orphan",
        order_by="SolicitudLinea.orden",
    )
    destinatarios: Mapped[list["SolicitudDestinatario"]] = relationship(
        back_populates="solicitud",
        cascade="all, delete-orphan",
    )


class EstadoDestinatario(StrEnum):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    RESPONDIDA = "respondida"
    DESCARTADA = "descartada"


class SolicitudDestinatario(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """A quién se le pide precio de un paquete. Uno por proveedor.

    Cada destinatario tiene su propio enlace, su propio estado y su propio
    presupuesto-oferta: los proveedores van a ritmos distintos y uno puede
    contestar mientras otro ni ha abierto el correo.
    """

    __tablename__ = "solicitud_destinatario"
    __table_args__ = (
        UniqueConstraint(
            "solicitud_id", "proveedor_id", name="solicitud_destinatario_unico"
        ),
        Index("ix_compras_solicitud_destinatario_solicitud", "solicitud_id"),
        Index("ix_compras_solicitud_destinatario_proveedor", "proveedor_id"),
        {"schema": SCHEMA},
    )

    solicitud_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_precios.id", ondelete="CASCADE"),
        nullable=False,
    )
    proveedor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.tercero.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # A qué correo se le manda, si no es el de la ficha del proveedor: el
    # comercial que lleva la cuenta, la dirección de ofertas… No se copia a la
    # ficha del tercero, que es su dato "oficial".
    email_destino: Mapped[str | None] = mapped_column(String(200), nullable=True)

    estado: Mapped[EstadoDestinatario] = mapped_column(
        enum_column(EstadoDestinatario, "estado_destinatario"),
        nullable=False,
        default=EstadoDestinatario.BORRADOR,
    )
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    respondida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # El presupuesto-oferta que se genera cuando este proveedor cierra su
    # respuesta. La FK va en este sentido (compras -> presupuestos) a
    # propósito: es la dirección que ya tiene el grafo de dependencias entre
    # módulos, y ponerla al revés obligaría a invertirlo.
    oferta_presupuesto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.presupuesto.id", ondelete="SET NULL"),
        nullable=True,
    )

    solicitud: Mapped["SolicitudPrecios"] = relationship(back_populates="destinatarios")
    ofertas: Mapped[list["OfertaLinea"]] = relationship(
        back_populates="destinatario", cascade="all, delete-orphan"
    )


class SolicitudLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una línea del paquete: QUÉ se pide. Común a todos los destinatarios.

    Es una copia congelada de la partida (o de un componente de su
    descompuesto) en el momento de añadirla: si el presupuesto se edita
    después, lo que los proveedores están cotizando no cambia bajo sus pies.
    `partida_id`/`concepto_id` quedan como rastro para poder volcar la oferta.

    Lo que oferta cada proveedor NO está aquí, sino en `OfertaLinea`: es un
    dato por proveedor, no de la línea.
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
    # Con `concepto_id` la línea NO pide la partida entera, sino UN componente
    # de su descompuesto (solo la mano de obra, solo el material, un
    # telefonillo concreto…). Se identifica por (partida, concepto) y no por la
    # fila del descompuesto a propósito: mientras la partida hereda el
    # descompuesto del banco esas filas son del concepto padre y su id cambia
    # en cuanto se independiza, así que no sirve como referencia estable.
    concepto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("presupuestos.concepto.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Copia congelada de la partida (o del componente).
    capitulo_resumen: Mapped[str | None] = mapped_column(String(250), nullable=True)
    codigo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False)
    texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    medicion: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=Decimal("0.000"))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # A qué destinatario se le adjudicó esta línea, si ya se decidió. Impide
    # adjudicar dos veces la misma partida a proveedores distintos, que
    # dejaría el descompuesto reescrito dos veces sin rastro de cuál manda.
    adjudicada_a_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_destinatario.id", ondelete="SET NULL"),
        nullable=True,
    )

    solicitud: Mapped[SolicitudPrecios] = relationship(back_populates="lineas")
    ofertas: Mapped[list["OfertaLinea"]] = relationship(
        back_populates="linea", cascade="all, delete-orphan"
    )


class OfertaLinea(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Lo que UN proveedor oferta por UNA línea del paquete.

    Sin `AutoriaMixin` a propósito: esto lo rellena el proveedor, que no es un
    usuario del sistema. Como consecuencia el listener de auditoría no mira
    esta tabla, así que el servicio graba un `AccionAuditoria.EVENTO` sobre la
    solicitud al guardar precios y al cerrar la respuesta.

    Las filas se crean SOLO cuando el proveedor escribe algo: la ausencia de
    fila es "no ha cotizado esta línea", que es justo el hueco que se enseña
    en el comparativo cuando alguien deja algo sin ofertar.
    """

    __tablename__ = "oferta_linea"
    __table_args__ = (
        UniqueConstraint("destinatario_id", "linea_id", name="oferta_linea_unica"),
        Index("ix_compras_oferta_linea_destinatario", "destinatario_id"),
        Index("ix_compras_oferta_linea_linea", "linea_id"),
        {"schema": SCHEMA},
    )

    destinatario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_destinatario.id", ondelete="CASCADE"),
        nullable=False,
    )
    linea_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_linea.id", ondelete="CASCADE"),
        nullable=False,
    )

    precio_ofertado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    observaciones_proveedor: Mapped[str | None] = mapped_column(Text, nullable=True)
    aprobada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    destinatario: Mapped[SolicitudDestinatario] = relationship(back_populates="ofertas")
    linea: Mapped[SolicitudLinea] = relationship(back_populates="ofertas")
    mediciones: Mapped[list["OfertaMedicion"]] = relationship(
        back_populates="oferta",
        cascade="all, delete-orphan",
        order_by="OfertaMedicion.orden",
    )
    descompuesto: Mapped[list["OfertaDescompuesto"]] = relationship(
        back_populates="oferta",
        cascade="all, delete-orphan",
        order_by="OfertaDescompuesto.orden",
    )


class OfertaMedicion(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """El estado de mediciones que aporta el PROVEEDOR para una línea.

    Mismo paradigma que `presupuestos.LineaMedicion` —comentario, uds, largo,
    ancho, alto, y el parcial como producto de lo informado— pero en su propia
    tabla y no en la del emisor: son la medición del proveedor, que puede no
    coincidir con la que se le pidió, y no deben tocar el presupuesto de
    cliente. Al cerrar la oferta se vuelcan como líneas de medición de su
    presupuesto-oferta.

    Sin fórmulas a propósito: el catálogo de fórmulas es del emisor.

    Sin `AutoriaMixin`, por el mismo motivo que `OfertaLinea`: esto lo rellena
    el proveedor, que no es un usuario del sistema.
    """

    __tablename__ = "oferta_medicion"
    __table_args__ = (
        Index("ix_compras_oferta_medicion_oferta", "oferta_linea_id"),
        {"schema": SCHEMA},
    )

    oferta_linea_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.oferta_linea.id", ondelete="CASCADE"),
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

    oferta: Mapped[OfertaLinea] = relationship(back_populates="mediciones")


class OfertaDescompuesto(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Cómo desglosa el proveedor su precio: mano de obra, materiales, medios.

    Mismo paradigma que `presupuestos.PartidaDescomposicion` —código,
    descripción, unidad, naturaleza, rendimiento, factor y precio— pero **sin
    ninguna referencia al banco de precios**: el banco es del emisor, y dar de
    alta conceptos desde aquí lo llenaría de fichas de sus proveedores. Todo
    va como texto congelado, que es lo que el proveedor está declarando.

    Si una línea tiene descompuesto, su `precio_ofertado` sale de la suma
    (rendimiento × factor × precio), igual que una partida con descompuesto
    propio en un presupuesto normal.

    Sin `AutoriaMixin`, por el mismo motivo que `OfertaLinea`: lo rellena el
    proveedor, que no es un usuario del sistema.
    """

    __tablename__ = "oferta_descompuesto"
    __table_args__ = (
        Index("ix_compras_oferta_descompuesto_oferta", "oferta_linea_id"),
        {"schema": SCHEMA},
    )

    oferta_linea_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.oferta_linea.id", ondelete="CASCADE"),
        nullable=False,
    )

    codigo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resumen: Mapped[str] = mapped_column(String(250), nullable=False, default="")
    unidad: Mapped[str] = mapped_column(String(10), nullable=False, default="ud")
    naturaleza: Mapped[str | None] = mapped_column(String(32), nullable=True)

    rendimiento: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, default=Decimal("1")
    )
    factor: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("1"))
    precio: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    oferta: Mapped[OfertaLinea] = relationship(back_populates="descompuesto")


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
    # Cuelga del DESTINATARIO, no del paquete: cada proveedor tiene su propio
    # enlace, y el token es lo que dice cuál de ellos está entrando.
    destinatario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_destinatario.id", ondelete="CASCADE"),
        nullable=False,
    )


class AccesoEstado(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Estado mutable del enlace del proveedor. Con RLS, a diferencia de
    `AccesoToken`: para cuando se lee esto la organización ya está fijada."""

    __tablename__ = "acceso_estado"
    __table_args__ = (
        UniqueConstraint("destinatario_id", name="acceso_estado_destinatario_unique"),
        {"schema": SCHEMA},
    )

    destinatario_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_destinatario.id", ondelete="CASCADE"),
        nullable=False,
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    usos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usos_ia: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ficheros_subidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ultimo_uso_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
