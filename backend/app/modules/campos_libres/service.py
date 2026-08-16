import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.campos_libres.models import CampoLibreDefinicion, CampoLibreValor, EntidadCampoLibre
from app.modules.campos_libres.schemas import CampoLibreDefinicionCreate, CampoLibreDefinicionUpdate


class ClaveDuplicada(Exception):
    pass


class DefinicionNoEncontrada(Exception):
    pass


async def listar_definiciones(
    session: AsyncSession, cuenta_id: uuid.UUID, entidad: EntidadCampoLibre, *, solo_activas: bool = False
) -> list[CampoLibreDefinicion]:
    condiciones = [CampoLibreDefinicion.cuenta_id == cuenta_id, CampoLibreDefinicion.entidad == entidad]
    if solo_activas:
        condiciones.append(CampoLibreDefinicion.activo.is_(True))
    filas = await session.execute(
        select(CampoLibreDefinicion).where(*condiciones).order_by(CampoLibreDefinicion.orden, CampoLibreDefinicion.etiqueta)
    )
    return list(filas.scalars())


async def crear_definicion(
    session: AsyncSession, cuenta_id: uuid.UUID, entidad: EntidadCampoLibre, datos: CampoLibreDefinicionCreate
) -> CampoLibreDefinicion:
    definicion = CampoLibreDefinicion(
        cuenta_id=cuenta_id,
        entidad=entidad,
        clave=datos.clave,
        etiqueta=datos.etiqueta,
        tipo=datos.tipo,
        opciones=datos.opciones,
        requerido=datos.requerido,
        orden=datos.orden,
    )
    session.add(definicion)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ClaveDuplicada(f"Ya existe un campo con la clave '{datos.clave}'") from exc
    return definicion


async def actualizar_definicion(
    session: AsyncSession,
    cuenta_id: uuid.UUID,
    entidad: EntidadCampoLibre,
    definicion_id: uuid.UUID,
    datos: CampoLibreDefinicionUpdate,
) -> CampoLibreDefinicion:
    definicion = await session.scalar(
        select(CampoLibreDefinicion).where(
            CampoLibreDefinicion.id == definicion_id,
            CampoLibreDefinicion.cuenta_id == cuenta_id,
            CampoLibreDefinicion.entidad == entidad,
        )
    )
    if definicion is None:
        raise DefinicionNoEncontrada(f"Campo '{definicion_id}' no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(definicion, campo, valor)
    await session.flush()
    return definicion


async def eliminar_definicion(
    session: AsyncSession, cuenta_id: uuid.UUID, entidad: EntidadCampoLibre, definicion_id: uuid.UUID
) -> bool:
    definicion = await session.scalar(
        select(CampoLibreDefinicion).where(
            CampoLibreDefinicion.id == definicion_id,
            CampoLibreDefinicion.cuenta_id == cuenta_id,
            CampoLibreDefinicion.entidad == entidad,
        )
    )
    if definicion is None:
        return False
    await session.delete(definicion)
    await session.flush()
    return True


# --- Valores (por registro, con RLS de organización) ---


async def obtener_valores(
    session: AsyncSession, organization_id: uuid.UUID, cuenta_id: uuid.UUID, entidad: EntidadCampoLibre, entidad_id: uuid.UUID
) -> dict[str, str | None]:
    filas = await session.execute(
        select(CampoLibreDefinicion.clave, CampoLibreValor.valor)
        .join(
            CampoLibreValor,
            (CampoLibreValor.definicion_id == CampoLibreDefinicion.id)
            & (CampoLibreValor.organization_id == organization_id)
            & (CampoLibreValor.entidad == entidad)
            & (CampoLibreValor.entidad_id == entidad_id),
            isouter=True,
        )
        .where(CampoLibreDefinicion.cuenta_id == cuenta_id, CampoLibreDefinicion.entidad == entidad)
    )
    return {clave: valor for clave, valor in filas.all()}


async def establecer_valores(
    session: AsyncSession,
    organization_id: uuid.UUID,
    cuenta_id: uuid.UUID,
    entidad: EntidadCampoLibre,
    entidad_id: uuid.UUID,
    valores: dict[str, str | None],
) -> None:
    definiciones = await listar_definiciones(session, cuenta_id, entidad)
    definicion_por_clave = {d.clave: d for d in definiciones}

    for clave, valor in valores.items():
        definicion = definicion_por_clave.get(clave)
        if definicion is None:
            continue  # clave desconocida (campo borrado entre tanto): se ignora, no se inventa una definición.
        existente = await session.scalar(
            select(CampoLibreValor).where(
                CampoLibreValor.organization_id == organization_id,
                CampoLibreValor.entidad == entidad,
                CampoLibreValor.entidad_id == entidad_id,
                CampoLibreValor.definicion_id == definicion.id,
            )
        )
        if existente is None:
            session.add(
                CampoLibreValor(
                    organization_id=organization_id,
                    entidad=entidad,
                    entidad_id=entidad_id,
                    definicion_id=definicion.id,
                    valor=valor,
                )
            )
        else:
            existente.valor = valor
    await session.flush()
