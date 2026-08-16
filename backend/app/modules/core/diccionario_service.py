import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.core.diccionario_models import EntradaDiccionario, TipoDiccionario
from app.modules.core.diccionario_schemas import EntradaDiccionarioCreate, EntradaDiccionarioUpdate


class ClaveDuplicada(Exception):
    pass


class EntradaNoEncontrada(Exception):
    pass


async def listar_entradas(
    session: AsyncSession, cuenta_id: uuid.UUID, tipo: TipoDiccionario, *, solo_activas: bool = False
) -> list[EntradaDiccionario]:
    condiciones = [EntradaDiccionario.cuenta_id == cuenta_id, EntradaDiccionario.tipo == tipo]
    if solo_activas:
        condiciones.append(EntradaDiccionario.activo.is_(True))
    filas = await session.execute(
        select(EntradaDiccionario)
        .where(*condiciones)
        .order_by(EntradaDiccionario.orden, EntradaDiccionario.etiqueta)
    )
    return list(filas.scalars())


async def crear_entrada(
    session: AsyncSession, cuenta_id: uuid.UUID, tipo: TipoDiccionario, datos: EntradaDiccionarioCreate
) -> EntradaDiccionario:
    entrada = EntradaDiccionario(
        cuenta_id=cuenta_id,
        tipo=tipo,
        clave=datos.clave,
        etiqueta=datos.etiqueta,
        valor=datos.valor,
        orden=datos.orden,
    )
    session.add(entrada)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ClaveDuplicada(f"Ya existe una entrada con la clave '{datos.clave}'") from exc
    return entrada


async def actualizar_entrada(
    session: AsyncSession, cuenta_id: uuid.UUID, entrada_id: uuid.UUID, datos: EntradaDiccionarioUpdate
) -> EntradaDiccionario:
    entrada = await session.scalar(
        select(EntradaDiccionario).where(
            EntradaDiccionario.id == entrada_id, EntradaDiccionario.cuenta_id == cuenta_id
        )
    )
    if entrada is None:
        raise EntradaNoEncontrada(f"Entrada '{entrada_id}' no encontrada")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(entrada, campo, valor)
    await session.flush()
    return entrada


async def eliminar_entrada(session: AsyncSession, cuenta_id: uuid.UUID, entrada_id: uuid.UUID) -> bool:
    entrada = await session.scalar(
        select(EntradaDiccionario).where(
            EntradaDiccionario.id == entrada_id, EntradaDiccionario.cuenta_id == cuenta_id
        )
    )
    if entrada is None:
        return False
    await session.delete(entrada)
    await session.flush()
    return True
