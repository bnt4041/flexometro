import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.compras.models import EstadoDestinatario, EstadoSolicitud


class ComponentePedido(BaseModel):
    """Un componente del descompuesto de una partida: solo la mano de obra,
    solo el material, un elemento concreto. Se identifica por la pareja
    partida+concepto porque mientras la partida hereda su descompuesto del
    banco, las filas de ese descompuesto son del concepto padre y su id
    cambia en cuanto se independiza."""

    partida_id: uuid.UUID
    concepto_id: uuid.UUID


class _SeleccionBase(BaseModel):
    partida_ids: list[uuid.UUID] = Field(default_factory=list)
    componentes: list[ComponentePedido] = Field(default_factory=list)

    @model_validator(mode="after")
    def _algo_que_pedir(self):
        if not self.partida_ids and not self.componentes:
            raise ValueError("Elige al menos una partida o un componente")
        return self


class SolicitudCrear(_SeleccionBase):
    presupuesto_id: uuid.UUID
    titulo: str = Field(min_length=1, max_length=200)
    proveedor_ids: list[uuid.UUID] = Field(default_factory=list)
    fecha_limite: date | None = None
    notas: str | None = Field(default=None, max_length=2000)


class SolicitudActualizar(BaseModel):
    """Todos los campos opcionales: solo se tocan los que el cliente mande
    (`model_dump(exclude_unset=True)` en el router) — así se puede llamar
    para cambiar solo la fecha límite sin arrastrarse las notas por delante."""

    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    notas: str | None = Field(default=None, max_length=2000)
    fecha_limite: date | None = None


class LineasActualizar(_SeleccionBase):
    pass


class DestinatarioCrear(BaseModel):
    proveedor_id: uuid.UUID
    email_destino: str | None = Field(default=None, max_length=200)


class DestinatarioActualizar(BaseModel):
    email_destino: str | None = Field(default=None, max_length=200)


class SolicitudLineaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partida_id: uuid.UUID | None
    # Relleno = la línea pide un componente del descompuesto, no la partida.
    concepto_id: uuid.UUID | None
    capitulo_resumen: str | None
    codigo: str | None
    resumen: str
    unidad: str
    medicion: Decimal
    # A qué destinatario se le adjudicó, si ya se decidió.
    adjudicada_a_id: uuid.UUID | None


class OfertaLineaOut(BaseModel):
    """Lo que un proveedor ha puesto en una línea. Que no exista significa que
    no la ha cotizado — el hueco del comparativo."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    linea_id: uuid.UUID
    precio_ofertado: Decimal | None
    observaciones_proveedor: str | None
    aprobada: bool


class DestinatarioOut(BaseModel):
    id: uuid.UUID
    proveedor_id: uuid.UUID
    proveedor_razon_social: str
    proveedor_email: str | None = None
    email_destino: str | None = None
    estado: EstadoDestinatario
    enviada_en: datetime | None
    respondida_en: datetime | None
    oferta_presupuesto_id: uuid.UUID | None
    ofertas: list[OfertaLineaOut] = Field(default_factory=list)


class SolicitudOut(BaseModel):
    id: uuid.UUID
    codigo: str
    titulo: str
    presupuesto_id: uuid.UUID
    estado: EstadoSolicitud
    fecha_limite: date | None
    notas: str | None
    lineas: list[SolicitudLineaOut] = Field(default_factory=list)
    destinatarios: list[DestinatarioOut] = Field(default_factory=list)


class EnlaceOut(BaseModel):
    """El enlace del proveedor solo existe en claro en el momento de
    emitirlo: aquí viaja una vez, para poder copiarlo, y nunca más."""

    enlace: str
