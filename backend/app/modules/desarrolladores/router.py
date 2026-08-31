import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import eventos as catalogo
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import ACCIONES, require_permiso
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.desarrolladores.claves import generar_clave
from app.modules.desarrolladores.enums import EstadoEntrega
from app.modules.desarrolladores.models import ClaveApi, EntregaWebhook, SuscripcionWebhook
from app.modules.desarrolladores.schemas import (
    ClaveApiCreada,
    ClaveApiIn,
    ClaveApiOut,
    ClaveApiUpdate,
    EntregaOut,
    WebhookIn,
    WebhookOut,
)

router = APIRouter(
    prefix="/api/desarrolladores",
    tags=["desarrolladores"],
    dependencies=[Depends(require_module("desarrolladores"))],
)


def _validar_ambitos(ambitos: dict) -> dict:
    """Deja los ámbitos en forma canónica y tira lo que no reconozca.

    Guardar tal cual lo que llegue haría que una errata («obas», «vero») se
    guardara como un permiso que no existe y que nadie entendería después.
    """
    from app.core.modules import registry

    codigos = registry.codes()
    limpios: dict[str, dict[str, str]] = {}
    for modulo, acciones in (ambitos or {}).items():
        if modulo not in codigos or not isinstance(acciones, dict):
            continue
        fila = {}
        for accion in ACCIONES:
            try:
                alcance = Alcance(acciones.get(accion, Alcance.NINGUNO))
            except ValueError:
                alcance = Alcance.NINGUNO
            fila[accion] = alcance.value
        if any(v != Alcance.NINGUNO.value for v in fila.values()):
            limpios[modulo] = fila
    return limpios


# ── Claves de API ───────────────────────────────────────────────────────


@router.get("/claves", response_model=list[ClaveApiOut])
async def listar_claves(
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "ver")),
) -> list[ClaveApiOut]:
    filas = await session.scalars(
        select(ClaveApi)
        .where(ClaveApi.organization_id == require_organization_id())
        .order_by(ClaveApi.created_at.desc())
    )
    return [ClaveApiOut.model_validate(f) for f in filas]


@router.post("/claves", response_model=ClaveApiCreada, status_code=status.HTTP_201_CREATED)
async def crear_clave(
    datos: ClaveApiIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "crear")),
) -> ClaveApiCreada:
    """El secreto se devuelve AQUÍ y solo aquí: de él únicamente se guarda su
    hash, así que no hay forma de volver a enseñarlo."""
    clave, prefijo, clave_hash = generar_clave()
    fila = ClaveApi(
        organization_id=require_organization_id(),
        nombre=datos.nombre,
        prefijo=prefijo,
        clave_hash=clave_hash,
        ambitos=_validar_ambitos(datos.ambitos),
        expira_en=(
            datetime.now(UTC) + timedelta(days=datos.dias_validez)
            if datos.dias_validez
            else None
        ),
        **datos_autoria(),
    )
    session.add(fila)
    await session.flush()
    return ClaveApiCreada(**ClaveApiOut.model_validate(fila).model_dump(), clave=clave)


@router.patch("/claves/{clave_id}", response_model=ClaveApiOut)
async def actualizar_clave(
    clave_id: uuid.UUID,
    datos: ClaveApiUpdate,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "editar")),
) -> ClaveApiOut:
    fila = await _clave(session, clave_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "ambitos" in cambios:
        cambios["ambitos"] = _validar_ambitos(cambios["ambitos"])
    for campo, valor in cambios.items():
        setattr(fila, campo, valor)
    await session.flush()
    return ClaveApiOut.model_validate(fila)


@router.delete("/claves/{clave_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revocar_clave(
    clave_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "borrar")),
) -> None:
    await session.delete(await _clave(session, clave_id))
    await session.flush()


async def _clave(session: AsyncSession, clave_id: uuid.UUID) -> ClaveApi:
    fila = await session.scalar(
        select(ClaveApi).where(
            ClaveApi.id == clave_id,
            ClaveApi.organization_id == require_organization_id(),
        )
    )
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrada")
    return fila


# ── Webhooks ────────────────────────────────────────────────────────────


@router.get("/eventos")
async def listar_eventos(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "ver")),
) -> list[dict]:
    """Los eventos a los que se puede suscribir un webhook: los mismos del
    catálogo que usan los avisos a personas."""
    from app.modules.core.service import active_module_codes

    activos = await active_module_codes(session, principal.organization_id)
    return [
        {
            "codigo": e.codigo,
            "modulo": e.modulo,
            "etiqueta": e.etiqueta,
            "descripcion": e.descripcion,
        }
        for e in catalogo.catalogo()
        if e.modulo in activos
    ]


async def _webhook(session: AsyncSession, webhook_id: uuid.UUID) -> SuscripcionWebhook:
    """La suscripción por id, o 404. El filtro por organización es explícito
    además del RLS: si algún día alguien consulta con una sesión sin política
    activa, el 404 sigue en pie."""
    fila = await session.scalar(
        select(SuscripcionWebhook).where(
            SuscripcionWebhook.id == webhook_id,
            SuscripcionWebhook.organization_id == require_organization_id(),
        )
    )
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook no encontrado")
    return fila


@router.get("/webhooks", response_model=list[WebhookOut])
async def listar_webhooks(
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "ver")),
) -> list[WebhookOut]:
    filas = await session.scalars(
        select(SuscripcionWebhook)
        .where(SuscripcionWebhook.organization_id == require_organization_id())
        .order_by(SuscripcionWebhook.nombre)
    )
    return [WebhookOut.model_validate(f) for f in filas]


@router.post("/webhooks", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
async def crear_webhook(
    datos: WebhookIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "crear")),
) -> WebhookOut:
    _exigir_https(datos.url)
    fila = SuscripcionWebhook(
        organization_id=require_organization_id(),
        nombre=datos.nombre,
        url=datos.url,
        eventos=_validar_eventos(datos.eventos),
        secreto=secrets.token_hex(24),
        activa=datos.activa,
        **datos_autoria(),
    )
    session.add(fila)
    await session.flush()
    return WebhookOut.model_validate(fila)


@router.put("/webhooks/{webhook_id}", response_model=WebhookOut)
async def actualizar_webhook(
    webhook_id: uuid.UUID,
    datos: WebhookIn,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "editar")),
) -> WebhookOut:
    _exigir_https(datos.url)
    fila = await _webhook(session, webhook_id)
    fila.nombre = datos.nombre
    fila.url = datos.url
    fila.eventos = _validar_eventos(datos.eventos)
    fila.activa = datos.activa
    await session.flush()
    return WebhookOut.model_validate(fila)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_webhook(
    webhook_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "borrar")),
) -> None:
    await session.delete(await _webhook(session, webhook_id))
    await session.flush()


@router.get("/webhooks/{webhook_id}/entregas", response_model=list[EntregaOut])
async def listar_entregas(
    webhook_id: uuid.UUID,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "ver")),
) -> list[EntregaOut]:
    """El registro de envíos. Se guardan también los que salieron bien: cuando
    una integración dice «no me llega nada», esto es lo único que permite
    saber quién tiene razón."""
    await _webhook(session, webhook_id)
    filas = await session.scalars(
        select(EntregaWebhook)
        .where(EntregaWebhook.suscripcion_id == webhook_id)
        .order_by(EntregaWebhook.created_at.desc())
        .limit(min(limit, 200))
    )
    return [EntregaOut.model_validate(f) for f in filas]


@router.post("/entregas/{entrega_id}/reintentar", response_model=EntregaOut)
async def reintentar_entrega(
    entrega_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    alcance: Alcance = Depends(require_permiso("desarrolladores", "editar")),
) -> EntregaOut:
    """Vuelve a poner en cola una entrega agotada, con el MISMO cuerpo que se
    intentó: recalcularlo días después mandaría otra cosa."""
    entrega = await session.scalar(
        select(EntregaWebhook).where(
            EntregaWebhook.id == entrega_id,
            EntregaWebhook.organization_id == require_organization_id(),
        )
    )
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrada")
    entrega.estado = EstadoEntrega.PENDIENTE
    entrega.intentos = 0
    entrega.proximo_intento_en = datetime.now(UTC)
    entrega.error = None
    await session.flush()
    return EntregaOut.model_validate(entrega)


def _validar_eventos(codigos: list[str]) -> list[str]:
    desconocidos = [c for c in codigos if catalogo.obtener(c) is None]
    if desconocidos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Eventos desconocidos: {', '.join(desconocidos)}",
        )
    return sorted(set(codigos))


def _exigir_https(url: str) -> None:
    """Un webhook lleva datos de negocio firmados. Por http viajarían en
    claro, y la firma no sirve de nada si cualquiera puede leer el cuerpo.

    Se deja pasar localhost porque es lo que se usa para probar en local, y
    ahí no hay red que escuchar."""
    if url.startswith("https://"):
        return
    if url.startswith("http://") and (
        "://localhost" in url or "://127.0.0.1" in url
    ):
        return
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "La URL tiene que ser https (o localhost para pruebas)",
    )
