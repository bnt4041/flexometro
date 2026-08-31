import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso
from app.core.tenancy import datos_autoria
from app.modules.automatizaciones import motor, nodos, service
from app.modules.automatizaciones.schemas import (
    AutomatizacionIn,
    AutomatizacionOut,
    EjecucionOut,
    TipoNodoOut,
)

# `router_privado` lleva la guarda de módulo; el público NO puede heredarla:
# un sistema de fuera recibiría un 404 confuso en vez de disparar el flujo, y
# además `require_module` necesita un principal que ahí no existe.
router_privado = APIRouter(
    prefix="/api/automatizaciones",
    tags=["automatizaciones"],
    dependencies=[Depends(require_module("automatizaciones"))],
)

#: Sin autenticar: es la URL que se le da a un sistema de fuera. Lo que la
#: autoriza es el token del enlace, igual que la separata del proveedor o el
#: enlace de firma. Va montado aparte para que NO herede las dependencias de
#: arriba — con `require_module` colgando, un sistema externo recibiría un
#: 404 confuso en vez de disparar el flujo.
publico_router = APIRouter(prefix="/api/publico/automatizacion", tags=["automatizaciones"])

#: Lo que monta el módulo: los dos, cada uno con sus reglas.
router = APIRouter()


def _salida(flujo, request: Request | None = None, token: str | None = None) -> AutomatizacionOut:
    salida = AutomatizacionOut.model_validate(flujo)
    salida.problemas = motor.validar(flujo.definicion or {})
    salida.token = token
    if token and request is not None:
        base = str(request.base_url).rstrip("/")
        salida.url_webhook = f"{base}/api/publico/automatizacion/{token}"
    return salida


@router_privado.get("/nodos", response_model=list[TipoNodoOut])
async def listar_nodos(
    alcance: Alcance = Depends(require_permiso("automatizaciones", "ver")),
) -> list[TipoNodoOut]:
    """Los tipos de nodo disponibles, con sus campos y sus salidas. El editor
    se dibuja entero a partir de esto: añadir un nodo nuevo no toca el
    frontend."""
    return [
        TipoNodoOut(
            tipo=t.tipo,
            categoria=t.categoria,
            etiqueta=t.etiqueta,
            descripcion=t.descripcion,
            icono=t.icono,
            campos=[c.__dict__ for c in t.campos],
            salidas=list(t.salidas),
        )
        for t in nodos.catalogo()
    ]


@router_privado.get("", response_model=list[AutomatizacionOut])
async def listar(
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "ver")),
) -> list[AutomatizacionOut]:
    return [_salida(f) for f in await service.listar(session)]


@router_privado.get("/{flujo_id}", response_model=AutomatizacionOut)
async def ver(
    flujo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "ver")),
) -> AutomatizacionOut:
    return _salida(await _flujo(session, flujo_id))


@router_privado.post("", response_model=AutomatizacionOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: AutomatizacionIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "crear")),
) -> AutomatizacionOut:
    try:
        flujo, token = await service.guardar(
            session, None,
            nombre=datos.nombre, descripcion=datos.descripcion,
            definicion=datos.definicion, activa=datos.activa, autoria=datos_autoria(),
        )
    except service.FlujoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _salida(flujo, request, token)


@router_privado.put("/{flujo_id}", response_model=AutomatizacionOut)
async def actualizar(
    flujo_id: uuid.UUID,
    datos: AutomatizacionIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "editar")),
) -> AutomatizacionOut:
    flujo = await _flujo(session, flujo_id)
    try:
        flujo, token = await service.guardar(
            session, flujo,
            nombre=datos.nombre, descripcion=datos.descripcion,
            definicion=datos.definicion, activa=datos.activa,
        )
    except service.FlujoInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _salida(flujo, request, token)


@router_privado.delete("/{flujo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar(
    flujo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "borrar")),
) -> None:
    await service.borrar(session, await _flujo(session, flujo_id))


@router_privado.post("/{flujo_id}/probar", response_model=EjecucionOut)
async def probar(
    flujo_id: uuid.UUID,
    entrada: dict | None = None,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "editar")),
) -> EjecucionOut:
    """Lo ejecuta a mano con los datos que se le den.

    Ojo: hace lo mismo que en real — si tiene un nodo de aviso, manda el
    aviso. No hay simulacro, porque un simulacro que no llama a nada no
    prueba lo que de verdad falla."""
    flujo = await _flujo(session, flujo_id)
    ejecucion = await motor.ejecutar(
        session, flujo, disparador="manual", entrada=entrada or {}
    )
    return EjecucionOut.model_validate(ejecucion)


@router_privado.get("/{flujo_id}/ejecuciones", response_model=list[EjecucionOut])
async def ejecuciones(
    flujo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("automatizaciones", "ver")),
) -> list[EjecucionOut]:
    await _flujo(session, flujo_id)
    return [EjecucionOut.model_validate(e) for e in await service.ejecuciones_de(session, flujo_id)]


async def _flujo(session: AsyncSession, flujo_id: uuid.UUID):
    flujo = await service.obtener(session, flujo_id)
    if flujo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrada")
    return flujo


@publico_router.post("/{token}")
async def disparar_webhook(
    token: str, datos: dict | None = None, session: AsyncSession = Depends(get_session)
) -> dict:
    """Arranca un flujo desde fuera. Siempre el mismo 404 si el token no vale:
    distinguir «no existe» de «desactivado» le diría a quien prueba tokens
    cuáles ha acertado."""
    from app.core.database import fijar_organizacion_activa

    flujo = await service.por_token(session, token)
    if flujo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    # El flujo corre en SU organización: esta petición llega sin sesión y sin
    # contexto, y sin fijarlo RLS no dejaría leer ni escribir nada.
    await fijar_organizacion_activa(session, flujo.organization_id)
    ejecucion = await motor.ejecutar(
        session, flujo, disparador="webhook", entrada=datos or {}
    )
    return {"ejecucion": str(ejecucion.id), "estado": ejecucion.estado.value}


router.include_router(router_privado)
router.include_router(publico_router)
