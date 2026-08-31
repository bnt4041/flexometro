"""Esquemas del módulo PRL.

El `estado` de un documento (vigente / por caducar / caducado) se calcula al
serializar y NO se guarda: ver el docstring de `models.DocumentoPRL`. Un
estado persistido mentiría en cuanto pasara un día sin que nadie tocara la
fila, que es precisamente cuando importa que no mienta.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.mensajeria import Canal, PreferenciaCanal
from app.modules.prl.models import (
    AmbitoPRL,
    EstadoFirma,
    EstadoFirmante,
    OrigenFirma,
    TipoRecurso,
)

#: Con cuánta antelación se avisa de una caducidad. 30 días es el margen con
#: el que da tiempo a renovar un reconocimiento médico o una ITV sin que el
#: trabajador o la máquina lleguen a quedarse parados.
DIAS_AVISO_CADUCIDAD = 30


class EstadoVigencia(StrEnum):
    VIGENTE = "vigente"
    POR_CADUCAR = "por_caducar"
    CADUCADO = "caducado"
    #: Registrado como exigible pero todavía sin fichero aportado.
    PENDIENTE = "pendiente"


def estado_de(fecha_caducidad: date | None, tiene_fichero: bool, hoy: date | None = None) -> EstadoVigencia:
    """Regla única de vigencia, en un solo sitio para que la lista, la ficha
    y los avisos no puedan discrepar entre sí."""
    referencia = hoy or date.today()
    if fecha_caducidad is None:
        return EstadoVigencia.PENDIENTE if not tiene_fichero else EstadoVigencia.VIGENTE
    if fecha_caducidad < referencia:
        return EstadoVigencia.CADUCADO
    if not tiene_fichero:
        return EstadoVigencia.PENDIENTE
    if (fecha_caducidad - referencia).days <= DIAS_AVISO_CADUCIDAD:
        return EstadoVigencia.POR_CADUCAR
    return EstadoVigencia.VIGENTE


# ── Recursos ────────────────────────────────────────────────────────────


class RecursoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    tipo: TipoRecurso = TipoRecurso.MAQUINARIA
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    matricula: str | None = Field(default=None, max_length=20)
    numero_serie: str | None = Field(default=None, max_length=60)
    anio_fabricacion: int | None = Field(default=None, ge=1900, le=2200)
    fecha_adquisicion: date | None = None
    obra_id: uuid.UUID | None = None
    responsable_id: uuid.UUID | None = None
    activo: bool = True
    notas: str | None = None


class RecursoCreate(RecursoBase):
    codigo: str | None = Field(default=None, max_length=32)


class RecursoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    tipo: TipoRecurso | None = None
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    matricula: str | None = Field(default=None, max_length=20)
    numero_serie: str | None = Field(default=None, max_length=60)
    anio_fabricacion: int | None = Field(default=None, ge=1900, le=2200)
    fecha_adquisicion: date | None = None
    obra_id: uuid.UUID | None = None
    responsable_id: uuid.UUID | None = None
    activo: bool | None = None
    notas: str | None = None


class RecursoOut(RecursoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    created_at: datetime
    updated_at: datetime


class RecursoResumen(RecursoOut):
    """Lo que necesita el listado sin abrir la ficha: dónde está, quién lo
    lleva y si tiene papeles caducados."""

    obra_nombre: str | None = None
    responsable_nombre: str | None = None
    documentos_caducados: int = 0
    documentos_por_caducar: int = 0


# ── Catálogo de tipos de documento ──────────────────────────────────────


class TipoDocumentoPRLBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    ambito: AmbitoPRL
    meses_validez: int = Field(default=12, ge=0, le=600)
    obligatorio: bool = False
    descripcion: str | None = None
    activo: bool = True


class TipoDocumentoPRLCreate(TipoDocumentoPRLBase):
    codigo: str | None = Field(default=None, max_length=40)


class TipoDocumentoPRLUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    ambito: AmbitoPRL | None = None
    meses_validez: int | None = Field(default=None, ge=0, le=600)
    obligatorio: bool | None = None
    descripcion: str | None = None
    activo: bool | None = None


class TipoDocumentoPRLOut(TipoDocumentoPRLBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str


# ── Documentos PRL ──────────────────────────────────────────────────────


class DocumentoPRLBase(BaseModel):
    tipo_id: uuid.UUID
    ambito: AmbitoPRL
    entidad_id: uuid.UUID | None = None
    fecha_emision: date | None = None
    fecha_caducidad: date
    notas: str | None = None


class DocumentoPRLCreate(DocumentoPRLBase):
    pass


class DocumentoPRLUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_id: uuid.UUID | None = None
    fecha_emision: date | None = None
    fecha_caducidad: date | None = None
    documento_id: uuid.UUID | None = None
    notas: str | None = None


class DocumentoPRLOut(DocumentoPRLBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    documento_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    # Rellenados por el servicio: el nombre del tipo evita una consulta por
    # fila en el cliente, y el estado es la regla de `estado_de`.
    tipo_nombre: str | None = None
    estado: EstadoVigencia | None = None
    dias_para_caducar: int | None = None
    nombre_archivo: str | None = None
    entidad_nombre: str | None = None


class ResumenVigencia(BaseModel):
    """Contadores para el semáforo de una obra, un recurso o la empresa."""

    total: int = 0
    vigentes: int = 0
    por_caducar: int = 0
    caducados: int = 0
    pendientes: int = 0
    #: Tipos marcados como obligatorios de los que no hay ningún documento.
    faltan_obligatorios: list[str] = []


# ── Plantillas ──────────────────────────────────────────────────────────


class PlantillaDocumentoBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    ambito: AmbitoPRL = AmbitoPRL.PROVEEDOR
    tipo_documento_id: uuid.UUID | None = None
    contenido: str = ""
    requiere_firma: bool = True
    activa: bool = True


class PlantillaDocumentoCreate(PlantillaDocumentoBase):
    codigo: str | None = Field(default=None, max_length=40)


class PlantillaDocumentoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    ambito: AmbitoPRL | None = None
    tipo_documento_id: uuid.UUID | None = None
    contenido: str | None = None
    requiere_firma: bool | None = None
    activa: bool | None = None


class PlantillaDocumentoOut(PlantillaDocumentoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    created_at: datetime
    updated_at: datetime


# ── Solicitudes de firma ────────────────────────────────────────────────


#: Marcadores que una plantilla puede usar y que se sustituyen al crear cada
#: solicitud. Se exponen por API para que el editor los enseñe en vez de
#: obligar a recordarlos — y para que esta lista y la sustitución real de
#: `firma._rellenar` no puedan divergir.
ETIQUETAS_PLANTILLA: list[dict[str, str]] = [
    {
        "etiqueta": "{{destinatario}}",
        "descripcion": "Nombre de la empresa o persona a la que se manda a firmar",
        "ejemplo": "Construcciones Ejemplo SL",
    },
    {
        "etiqueta": "{{obra}}",
        "descripcion": "Nombre de la obra, si la solicitud se crea desde una",
        "ejemplo": "Reforma Calle Mayor 12",
    },
    {
        "etiqueta": "{{emisor}}",
        "descripcion": "Nombre de tu organización",
        "ejemplo": "Obras y Reformas SA",
    },
    {
        "etiqueta": "{{fecha}}",
        "descripcion": "Fecha en que se crea la solicitud",
        "ejemplo": "29/08/2026",
    },
]


class EtiquetaPlantilla(BaseModel):
    etiqueta: str
    descripcion: str
    ejemplo: str


class FirmanteIn(BaseModel):
    """Una persona a la que pedir firma. Puede venir de la agenda
    (`contacto_id`) o escribirse a mano; en los dos casos nombre y correo se
    copian y se guardan, porque son evidencia."""

    nombre: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=200)
    #: Opcional. Con teléfono, el enlace va por WhatsApp y el código de
    #: verificación por correo — dos canales, que es lo que hace que el
    #: segundo factor signifique algo.
    telefono: str | None = Field(default=None, max_length=30)
    contacto_id: uuid.UUID | None = None
    #: Si se marca y no venía de la agenda, se da de alta como contacto para
    #: poder reutilizarlo la próxima vez.
    guardar_como_contacto: bool = False
    #: Empresa a la que asociar el contacto nuevo, si se guarda.
    tercero_id: uuid.UUID | None = None


class FirmanteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    orden: int
    nombre: str
    email: str
    telefono: str | None = None
    #: Por dónde se le mandó el enlace. Vacío mientras no se le haya mandado.
    canales_envio: list[Canal] | None = None
    contacto_id: uuid.UUID | None = None
    estado: EstadoFirmante
    enviada_en: datetime | None = None
    vista_en: datetime | None = None
    firmada_en: datetime | None = None
    firmante_nombre: str | None = None
    firmante_dni: str | None = None
    motivo_rechazo: str | None = None
    posiciones_firma: list[dict] | None = None
    #: Solo en la ficha del emisor, para poder enseñar la firma sin bajar el PDF.
    firma_imagen: str | None = None
    ip_firma: str | None = None


class SolicitudFirmaCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    #: Tres orígenes posibles, por orden de prioridad al resolverlos: un PDF
    #: que ya existe en el gestor documental (subido ahora o cogido de la
    #: biblioteca), una plantilla, o HTML escrito a mano.
    documento_origen_id: uuid.UUID | None = None
    plantilla_id: uuid.UUID | None = None
    contenido_html: str | None = None
    obra_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    #: Quién tiene que firmar. Al menos uno; pueden ser varios y todos pueden
    #: firmar a la vez (no hay turnos).
    firmantes: list[FirmanteIn] = Field(min_length=1)
    #: Días que el enlace sigue siendo válido desde el envío.
    dias_validez: int = Field(default=30, ge=1, le=365)
    #: Por dónde mandar el enlace y por dónde el código de verificación.
    #: `auto` deja decidir al dominio, que es lo razonable casi siempre.
    canal_enlace: PreferenciaCanal = PreferenciaCanal.AUTO
    canal_codigo: PreferenciaCanal = PreferenciaCanal.AUTO


class SolicitudFirmaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    contenido_html: str | None = None
    obra_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None



class SolicitudFirmaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    titulo: str
    estado: EstadoFirma
    origen: OrigenFirma = OrigenFirma.HTML
    documento_origen_id: uuid.UUID | None = None
    obra_id: uuid.UUID | None = None
    tercero_id: uuid.UUID | None = None
    enviada_en: datetime | None = None
    expira_en: datetime | None = None
    documento_id: uuid.UUID | None = None
    #: Cómo se decidió mandar el enlace y el código en esta solicitud.
    canal_enlace: PreferenciaCanal = PreferenciaCanal.AUTO
    canal_codigo: PreferenciaCanal = PreferenciaCanal.AUTO
    created_at: datetime
    obra_nombre: str | None = None
    tercero_nombre: str | None = None
    #: Resumen para el listado, sin tener que traer los firmantes enteros.
    total_firmantes: int = 0
    firmas_hechas: int = 0
    firmantes: list[FirmanteOut] = []


class SolicitudFirmaDetalle(SolicitudFirmaOut):
    contenido_html: str = ""
    #: SHA-256 de lo que se firmó — permite verificar después que un PDF es
    #: exactamente ese y no otro.
    hash_documento: str | None = None


class PosicionFirma(BaseModel):
    pagina: int = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    ancho: float = Field(gt=0, le=1, default=0.25)
    alto: float = Field(gt=0, le=1, default=0.08)


class PosicionesFirmanteIn(BaseModel):
    """Dónde firma cada persona, en fracciones de 0 a 1 del tamaño de página
    — no en puntos, para no depender de a qué escala se pintó el visor."""

    firmante_id: uuid.UUID
    posiciones: list[PosicionFirma] = []


class PosicionesFirmaIn(BaseModel):
    por_firmante: list[PosicionesFirmanteIn] = []


class EnvioFirmaOut(BaseModel):
    #: A quién iba este envío — con varios firmantes hace falta para saber
    #: cuál de los correos falló.
    firmante_nombre: str = ""

    """`enviado=False` con `error` relleno NO es un fallo del endpoint: la
    solicitud queda creada y el enlace es válido igual — lo que ha fallado es
    el correo, y el usuario puede copiar el enlace y mandarlo por su cuenta.
    Mismo criterio que `PruebaSmtpOut` en core."""

    enviado: bool
    #: Por qué canales salió de verdad. Puede no coincidir con lo pedido: en
    #: automático, si el preferido falla se reintenta por el otro.
    canales: list[Canal] = Field(default_factory=list)
    error: str | None = None
    enlace: str


# ── Espacio público de firma (sin sesión) ───────────────────────────────


class DocumentoParaFirmar(BaseModel):
    """Lo que ve quien abre el enlace. Deliberadamente escueto: no lleva
    identificadores internos, ni el tercero, ni nada de la organización más
    allá de su nombre — quien firma no tiene por qué ver el resto."""

    titulo: str
    #: Con `origen` PDF esto va vacío y el documento se pide aparte, en
    #: `/api/publico/firma/{token}/documento`.
    origen: OrigenFirma = OrigenFirma.HTML
    contenido_html: str
    #: A quién va dirigido ESTE enlace.
    destinatario_nombre: str
    emisor: str
    estado: EstadoFirma
    #: Estado de este firmante en concreto (el de arriba es del documento).
    mi_estado: EstadoFirmante = EstadoFirmante.PENDIENTE
    #: Los demás firmantes y cómo van — sin correos ni datos de contacto.
    otros_firmantes: list["ResumenFirmante"] = []
    firmada_en: datetime | None = None
    expira_en: datetime | None = None
    #: Dónde irá la firma, para que el visor del firmante se lo enseñe.
    posiciones_firma: list[dict] | None = None


class ResumenFirmante(BaseModel):
    """Lo mínimo para que quien firma sepa quién más tiene que hacerlo. Sin
    correo ni identificadores: no tiene por qué ver la agenda de quien envía."""

    nombre: str
    estado: EstadoFirmante
    firmada_en: datetime | None = None


class FirmarIn(BaseModel):
    firmante_nombre: str = Field(min_length=1, max_length=160)
    firmante_dni: str | None = Field(default=None, max_length=20)
    #: PNG en data: URI del trazo dibujado en el navegador.
    firma_imagen: str = Field(min_length=1)
    #: Código de un solo uso que se mandó al correo del destinatario. Es el
    #: segundo factor: sin él, el enlace por sí solo bastaría para firmar.
    codigo: str = Field(min_length=4, max_length=10)


class CodigoEnviadoOut(BaseModel):
    enviado: bool
    #: Dónde se ha mandado, ofuscado (`b***@gmail.com`, `···233`): confirma al
    #: firmante dónde mirar sin exponer la dirección entera a quien tenga el
    #: enlace en la mano.
    destino: str
    #: Por qué canales ha salido. La pantalla lo necesita para decir «mira tu
    #: correo» o «mira tu WhatsApp», que no es lo mismo.
    canales: list[Canal] = Field(default_factory=list)
    error: str | None = None


class RechazarIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=1000)


class ResultadoFirmaOut(BaseModel):
    estado: EstadoFirma
    mensaje: str
    #: `True` cuando esta firma era la última y el documento queda cerrado.
    completado: bool = False


# ── Ficha PRL de una obra ───────────────────────────────────────────────


class FichaPRLObra(BaseModel):
    """Todo lo que la pestaña PRL de una obra necesita en una sola llamada:
    sus documentos, el semáforo y las firmas pendientes."""

    documentos: list[DocumentoPRLOut] = []
    resumen: ResumenVigencia
    firmas: list[SolicitudFirmaOut] = []
    #: Trabajadores asignados a la obra con algún papel caducado o por
    #: caducar: es la pregunta que de verdad se hace antes de una visita de
    #: la inspección.
    personal_con_avisos: list["AvisoPersonal"] = []


class AvisoPersonal(BaseModel):
    personal_id: uuid.UUID
    nombre: str
    motivos: list[str] = []


class PersonalPRLOut(BaseModel):
    """Vista de PRL de un trabajador, para el listado de vigilancia."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    nombre: str
    apellidos: str | None = None
    categoria: str | None = None
    activo: bool
    tpc_caducidad: date | None = None
    proximo_reconocimiento: date | None = None
    aptitud_medica: str | None = None
    formacion_prl_horas: int | None = None
    es_recurso_preventivo: bool = False
    documentos_caducados: int = 0
    documentos_por_caducar: int = 0


# `DocumentoParaFirmar` referencia `ResumenFirmante` antes de declararla.
DocumentoParaFirmar.model_rebuild()
FichaPRLObra.model_rebuild()
