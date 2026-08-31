"""Los dos endpoints del copiloto: hablar y confirmar.

Están separados a propósito. `/conversar` no escribe nada nunca — como mucho
devuelve una propuesta. `/confirmar` es el único que escribe, y solo con lo
que la persona ha visto y aceptado.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.tenancy import require_organization_id
from app.modules.ia.copiloto import conversacion, ejecutores
from app.modules.ia.deepseek import DeepSeekError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copiloto", tags=["ia"])

#: Tope de historial que se acepta del navegador. No es una preferencia de
#: estilo: cada mensaje viaja al modelo y se paga, y el cliente podría mandar
#: mil.
MAX_MENSAJES = 30


class MensajeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: str = Field(pattern="^(user|assistant)$")
    contenido: str = Field(min_length=1, max_length=4000)


class ConversarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mensajes: list[MensajeIn] = Field(min_length=1, max_length=MAX_MENSAJES)
    #: Dónde está la persona. Sirve para orientarla y para rellenar el origen
    #: de un ticket sin preguntárselo.
    ruta_actual: str | None = Field(default=None, max_length=400)


class CampoPropuesta(BaseModel):
    etiqueta: str
    valor: str


class PropuestaOut(BaseModel):
    accion: str
    resumen: str
    datos: dict
    campos: list[CampoPropuesta]


class RespuestaCopiloto(BaseModel):
    respuesta: str
    propuesta: PropuestaOut | None = None


class ConfirmarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accion: str = Field(max_length=80)
    datos: dict


class ConfirmadaOut(BaseModel):
    descripcion: str
    ruta: str | None = None


@router.post("/conversar", response_model=RespuestaCopiloto)
async def conversar(
    datos: ConversarIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> RespuestaCopiloto:
    from app.modules.core import billing_service

    org_id = require_organization_id()
    try:
        turno = await conversacion.conversar(
            session,
            principal,
            [{"role": m.rol, "content": m.contenido} for m in datos.mensajes],
            ruta_actual=datos.ruta_actual,
        )
    except DeepSeekError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    # Un turno puede haber dado varias vueltas al modelo; se factura una vez,
    # ya sumado, no una fila por cada búsqueda interna.
    await billing_service.registrar_uso_ia(
        session,
        organization_id=org_id,
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
        proveedor="deepseek",
        modelo=turno.modelo,
        tokens_entrada=turno.tokens_entrada,
        tokens_salida=turno.tokens_salida,
        referencia=None,
    )

    propuesta = (
        PropuestaOut(
            accion=turno.propuesta.accion,
            resumen=turno.propuesta.resumen,
            datos=turno.propuesta.datos,
            campos=[CampoPropuesta(**c) for c in turno.propuesta.campos],
        )
        if turno.propuesta
        else None
    )
    return RespuestaCopiloto(respuesta=turno.respuesta, propuesta=propuesta)


@router.post("/confirmar", response_model=ConfirmadaOut)
async def confirmar(
    datos: ConfirmarIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> ConfirmadaOut:
    """Aplica una propuesta. El permiso se comprueba dentro, otra vez: lo que
    llega aquí ha pasado por el navegador y no se cree nada de él salvo qué
    se pidió hacer."""
    try:
        aplicada = await ejecutores.aplicar(session, principal, datos.accion, datos.datos)
    except ejecutores.PropuestaInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ConfirmadaOut(descripcion=aplicada.descripcion, ruta=aplicada.ruta)
