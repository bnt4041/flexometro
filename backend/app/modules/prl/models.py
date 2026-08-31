"""PRL (prevención de riesgos laborales) y recursos de la empresa.

Tres piezas que en la práctica son la misma preocupación —demostrar que algo
está en regla y sigue estándolo—, y por eso viven juntas:

1. **`Recurso`**: vehículos, maquinaria y equipos. No es un inventario
   contable: existe porque un camión o una hormigonera tienen documentación
   que caduca (ITV, seguro, marcado CE, revisiones) exactamente igual que la
   tiene una persona, y en una inspección se piden igual.

2. **`DocumentoPRL`**: la caducidad es el motivo de todo el módulo. Un
   certificado de formación caducado es, a efectos legales, lo mismo que no
   tenerlo — así que `fecha_caducidad` es obligatoria y el estado (vigente /
   por caducar / caducado) se CALCULA a partir de ella en cada lectura, nunca
   se guarda: un estado persistido se queda obsoleto en cuanto pasa un día
   sin que nadie toque la fila.

3. **`SolicitudFirma`**: la coordinación de actividades empresariales (RD
   171/2004) obliga a recabar documentación de cada subcontrata y a dejar
   constancia. Aquí se manda al proveedor un documento a firmar y se guarda
   la evidencia.

El catálogo (`TipoDocumentoPRL`) es dato, no código: cada organización
requiere documentos distintos según su actividad, y la legislación cambia sin
avisar. La migración inicial siembra los tipos habituales del sector de la
construcción en España, pero son editables.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import enum_column
from app.core.mensajeria import PreferenciaCanal
from app.core.models import (
    AutoriaMixin,
    Base,
    OrganizationMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

SCHEMA = "prl"


class AmbitoPRL(StrEnum):
    """A qué cuelga un documento PRL. `EMPRESA` es el único sin entidad
    concreta: son los papeles de la organización entera (concierto con el
    servicio de prevención, evaluación de riesgos, seguro de RC...)."""

    EMPRESA = "empresa"
    PERSONAL = "personal"
    RECURSO = "recurso"
    OBRA = "obra"
    PROVEEDOR = "proveedor"


class TipoRecurso(StrEnum):
    VEHICULO = "vehiculo"
    MAQUINARIA = "maquinaria"
    HERRAMIENTA = "herramienta"
    EPI = "epi"
    OTRO = "otro"


class EstadoFirma(StrEnum):
    """Estado del DOCUMENTO, agregado de sus firmantes.

    `PARCIAL` es el que hace falta al haber varios: el documento ya tiene
    firmas válidas pero todavía no está cerrado, y eso no es ni "enviada" ni
    "firmada". Sin ese estado no se puede distinguir «nadie ha firmado» de
    «faltan dos de cinco»."""

    BORRADOR = "borrador"
    ENVIADA = "enviada"
    VISTA = "vista"
    PARCIAL = "parcial"
    FIRMADA = "firmada"
    RECHAZADA = "rechazada"
    CANCELADA = "cancelada"


class EstadoFirmante(StrEnum):
    """Estado de UNA persona dentro del documento."""

    PENDIENTE = "pendiente"
    VISTA = "vista"
    FIRMADA = "firmada"
    RECHAZADA = "rechazada"


class OrigenFirma(StrEnum):
    """De dónde sale el documento que se manda a firmar.

    `PLANTILLA` y `HTML` acaban igual —un HTML que se convierte a PDF al
    firmar—, y se distinguen solo para saber de dónde vino. `PDF` es otra
    cosa: el documento ya existe como fichero (subido en el momento o cogido
    del gestor documental) y NO se regenera, se firma tal cual. Eso importa
    porque un PDF que ya circuló (un contrato, un plan de seguridad) tiene que
    llegar al firmante byte a byte como está, no reconstruido."""

    PLANTILLA = "plantilla"
    HTML = "html"
    PDF = "pdf"


class Recurso(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un vehículo, una máquina o un equipo. `matricula` y `numero_serie` son
    ambos opcionales porque identifican cosas distintas (un camión tiene
    matrícula; una hormigonera, número de bastidor) y casi ningún recurso
    tiene los dos."""

    __tablename__ = "recurso"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="recurso_codigo_unique"),
        Index("ix_prl_recurso_obra", "obra_id"),
        Index("ix_prl_recurso_responsable", "responsable_id"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    tipo: Mapped[TipoRecurso] = mapped_column(
        enum_column(TipoRecurso, "tipo_recurso"), nullable=False, default=TipoRecurso.MAQUINARIA
    )

    marca: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    matricula: Mapped[str | None] = mapped_column(String(20), nullable=True)
    numero_serie: Mapped[str | None] = mapped_column(String(60), nullable=True)
    anio_fabricacion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_adquisicion: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Dónde está y quién responde de él. SET NULL en los dos: cerrar una obra
    # o dar de baja a alguien no debe borrar el recurso ni su documentación.
    obra_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("obras.obra.id", ondelete="SET NULL"), nullable=True
    )
    responsable_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("obras.personal.id", ondelete="SET NULL"), nullable=True
    )

    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class TipoDocumentoPRL(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Catálogo editable de qué documentos se exigen y cuánto duran.

    `meses_validez` es lo que permite proponer la caducidad sola al registrar
    un documento (un reconocimiento médico vale 12 meses, una ITV de turismo
    24...). Es una propuesta, no una imposición: la fecha real la manda
    siempre el papel, así que el usuario puede corregirla."""

    __tablename__ = "tipo_documento_prl"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="tipo_documento_prl_codigo_unique"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    ambito: Mapped[AmbitoPRL] = mapped_column(enum_column(AmbitoPRL, "ambito_prl"), nullable=False)
    meses_validez: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    # Marca los que hay que tener sí o sí: es lo que alimenta el aviso de «a
    # esta obra le falta documentación» sin tener que codificar la lista.
    obligatorio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DocumentoPRL(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un documento concreto, ya aportado o pendiente de aportar.

    `entidad_id` es polimórfico y sin clave ajena, igual que en
    `documentos.Documento`: apunta a un `personal`, un `recurso`, una `obra` o
    un `tercero` según `ambito`, y es NULL cuando el ámbito es EMPRESA. Una FK
    real exigiría una columna por tipo y el modelo dejaría de ser extensible
    sin migración cada vez que aparece un ámbito nuevo.

    `documento_id` apunta al fichero en el gestor documental y es opcional a
    propósito: registrar que FALTA un documento (con su fecha límite) es tan
    útil como registrar que se tiene."""

    __tablename__ = "documento_prl"
    __table_args__ = (
        Index("ix_prl_documento_ambito", "organization_id", "ambito", "entidad_id"),
        Index("ix_prl_documento_caducidad", "organization_id", "fecha_caducidad"),
        {"schema": SCHEMA},
    )

    tipo_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.tipo_documento_prl.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ambito: Mapped[AmbitoPRL] = mapped_column(enum_column(AmbitoPRL, "ambito_prl"), nullable=False)
    entidad_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    fecha_emision: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Obligatoria por decisión de producto: el módulo entero existe para
    # avisar de lo que caduca, y un documento sin fecha se queda fuera de todo
    # aviso — que es justo el fallo que se quiere evitar.
    fecha_caducidad: Mapped[date] = mapped_column(Date, nullable=False)

    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documentos.documento.id", ondelete="SET NULL"),
        nullable=True,
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlantillaDocumento(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Patrón de documento reutilizable (acta de coordinación, entrega de
    EPIs, información de riesgos...).

    `contenido` es HTML con marcadores `{{...}}` que se sustituyen al generar
    la solicitud de firma. Se guarda saneado (ver `service.py`): lo edita un
    usuario con un editor enriquecido y acaba renderizándose en una página
    pública, así que HTML sin filtrar aquí sería XSS servido a un tercero."""

    __tablename__ = "plantilla_documento"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="plantilla_documento_codigo_unique"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    ambito: Mapped[AmbitoPRL] = mapped_column(
        enum_column(AmbitoPRL, "ambito_prl"), nullable=False, default=AmbitoPRL.PROVEEDOR
    )
    tipo_documento_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.tipo_documento_prl.id", ondelete="SET NULL"),
        nullable=True,
    )
    contenido: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requiere_firma: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SolicitudFirma(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, AutoriaMixin, Base):
    """Un documento mandado a firmar a un tercero, con su evidencia.

    `contenido_html` es una FOTO del documento en el momento de enviarlo, no
    una referencia a la plantilla: si alguien edita la plantilla después, lo
    que se firmó tiene que seguir siendo exactamente lo que el firmante vio.
    Sin esta copia, la evidencia no valdría para nada.

    Los campos de evidencia (`firma_imagen`, `ip_firma`, `user_agent_firma`,
    los tres sellos de tiempo) son lo que convierte esto en una firma
    electrónica simple con trazabilidad, en el sentido del art. 3 de eIDAS.
    No es firma avanzada ni cualificada: no hay certificado del firmante."""

    __tablename__ = "solicitud_firma"
    __table_args__ = (
        UniqueConstraint("organization_id", "codigo", name="solicitud_firma_codigo_unique"),
        Index("ix_prl_solicitud_firma_obra", "obra_id"),
        Index("ix_prl_solicitud_firma_estado", "organization_id", "estado"),
        {"schema": SCHEMA},
    )

    codigo: Mapped[str] = mapped_column(String(32), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    origen: Mapped[OrigenFirma] = mapped_column(
        enum_column(OrigenFirma, "origen_firma"), nullable=False, default=OrigenFirma.HTML
    )
    #: Vacío cuando el origen es un PDF: ahí el documento es el fichero.
    contenido_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: El PDF que se manda a firmar, cuando `origen` es PDF. RESTRICT y no
    #: SET NULL a propósito: si se borrara el fichero, la solicitud se quedaría
    #: sin poder decir QUÉ se firmó — y eso es justo lo que la evidencia tiene
    #: que poder demostrar.
    documento_origen_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documentos.documento.id", ondelete="RESTRICT"),
        nullable=True,
    )

    plantilla_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.plantilla_documento.id", ondelete="SET NULL"),
        nullable=True,
    )
    obra_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("obras.obra.id", ondelete="SET NULL"), nullable=True
    )
    tercero_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("terceros.tercero.id", ondelete="SET NULL"), nullable=True
    )
    estado: Mapped[EstadoFirma] = mapped_column(
        enum_column(EstadoFirma, "estado_firma"), nullable=False, default=EstadoFirma.BORRADOR
    )
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Por dónde mandar el enlace y por dónde el código, elegido por quien
    #: crea la solicitud. Valen para todos sus firmantes: son una decisión
    #: del documento («esto va por WhatsApp»), no de cada persona.
    #:
    #: `AUTO` (lo de fábrica) deja decidir al dominio: el enlace por WhatsApp
    #: si hay móvil, y el código por un canal que el enlace no haya usado.
    canal_enlace: Mapped[PreferenciaCanal] = mapped_column(
        enum_column(PreferenciaCanal, "preferencia_canal"),
        nullable=False,
        default=PreferenciaCanal.AUTO,
    )
    canal_codigo: Mapped[PreferenciaCanal] = mapped_column(
        enum_column(PreferenciaCanal, "preferencia_canal"),
        nullable=False,
        default=PreferenciaCanal.AUTO,
    )

    #: SHA-256 del documento EXACTO que se firmó. Es lo que permite demostrar
    #: después que un PDF dado es ese y no otro: cualquier modificación
    #: posterior cambia el hash.
    hash_documento: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: PDF sellado que se genera al firmar, ya en el gestor documental.
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documentos.documento.id", ondelete="SET NULL"),
        nullable=True,
    )


class Firmante(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Una persona que tiene que firmar un documento, con SU evidencia.

    Existe como tabla aparte —y no como columnas de `SolicitudFirma`— porque
    un mismo documento puede necesitar varias firmas (el contratista, la
    subcontrata y el coordinador de seguridad en un acta de coordinación), y
    cada una es un acto independiente: su propio enlace, su propio código de
    verificación, su propia IP y su propio sello de tiempo. Meter dos firmas
    en una fila obligaría a duplicar columnas y haría imposible una tercera.

    `nombre` y `email` se COPIAN aquí aunque venga de un contacto: a quién se
    le pidió la firma y a qué correo se le mandó son datos de la evidencia, y
    editar la ficha del contacto meses después no puede reescribirlos.
    `contacto_id` queda solo como referencia de dónde salió."""

    __tablename__ = "firmante"
    __table_args__ = (
        Index("ix_prl_firmante_solicitud", "solicitud_id"),
        {"schema": SCHEMA},
    )

    solicitud_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.solicitud_firma.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: En qué orden se listan. NO impone firma secuencial: todos pueden firmar
    #: a la vez. Imponer turnos sería otra decisión y no la que hace falta aquí.
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Opcional. Si lo hay y el puente de WhatsApp está activo, el enlace va
    #: por ahí (llega al momento y no acaba en spam) y el código de
    #: verificación por correo. Sin teléfono, todo va por correo como antes.
    telefono: Mapped[str | None] = mapped_column(String(30), nullable=True)
    #: Por dónde se le mandó el enlace DE VERDAD (puede ser más de un canal).
    #:
    #: No es solo traza: en modo automático decide por dónde va después el
    #: código de verificación, que va siempre por un canal que el enlace no
    #: haya usado. Si el enlace y su código llegan al mismo sitio, quien tenga
    #: acceso a ese canal tiene las dos mitades y el segundo factor deja de
    #: serlo.
    canales_envio: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    #: De dónde salió, si se eligió de la agenda. SET NULL: borrar el contacto
    #: no puede borrar una firma ya hecha.
    contacto_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("terceros.contacto.id", ondelete="SET NULL"),
        nullable=True,
    )

    estado: Mapped[EstadoFirmante] = mapped_column(
        enum_column(EstadoFirmante, "estado_firmante"),
        nullable=False,
        default=EstadoFirmante.PENDIENTE,
    )
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vista_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    firmada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Lo que el firmante declaró al firmar, que puede no coincidir con
    #: `nombre` (firma otra persona de la misma empresa) — y eso también es
    #: evidencia.
    firmante_nombre: Mapped[str | None] = mapped_column(String(160), nullable=True)
    firmante_dni: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: PNG en data: URI del trazo dibujado.
    firma_imagen: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_firma: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent_firma: Mapped[str | None] = mapped_column(String(400), nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Segundo factor, por firmante: cada uno verifica SU buzón.
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_expira_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    otp_verificado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Dónde va SU firma en el PDF (fracciones 0-1 del tamaño de página):
    #: `[{"pagina": 0, "x": 0.6, "y": 0.1, "ancho": 0.25, "alto": 0.08}]`.
    #: Con varios firmantes cada uno tiene su recuadro, así que esto va aquí
    #: y no en la solicitud.
    posiciones_firma: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    #: Aviso de "ya han firmado los demás" que se le mandó al firmar otro:
    #: evita reenviar el mismo aviso dos veces si se reintenta.
    ultimo_aviso_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FirmaToken(UUIDPrimaryKeyMixin, OrganizationMixin, TimestampMixin, Base):
    """Resolución del enlace de firma: token -> organización.

    ⚠️ FUERA DE RLS, por el mismo motivo exacto que `compras.acceso_token`
    (ver su docstring, que explica el problema a fondo): quien firma llega sin
    sesión, así que hay que saber a qué organización pertenece el enlace ANTES
    de que exista contexto, y sin contexto cualquier tabla con RLS devuelve
    cero filas.

    Se queda en lo mínimo y opaco: un hash y una referencia. Todo el estado
    mutable (caducidad, estado de la firma) vive en `SolicitudFirma`, que SÍ
    tiene RLS y se lee ya dentro del contexto.

    Nunca se guarda el token en claro: solo su SHA-256. El token viaja
    únicamente en el correo al firmante."""

    __tablename__ = "firma_token"
    __table_args__ = (
        UniqueConstraint("token_hash", name="firma_token_hash_unique"),
        {"schema": SCHEMA},
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Cuelga del FIRMANTE, no del documento: con varias personas firmando,
    #: cada una tiene su propio enlace y el token es lo que dice cuál de ellas
    #: está entrando. Mismo criterio que `compras.acceso_token`, que cuelga
    #: del destinatario y no de la solicitud de precios.
    firmante_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.firmante.id", ondelete="CASCADE"),
        nullable=False,
    )
