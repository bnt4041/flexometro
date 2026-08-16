import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.numeracion import PATRON_POR_DEFECTO, PatronInvalido, validar_patron
from app.modules.core.cuenta_schemas import (
    CuentaCreate,
    CuentaUpdate,
    PatronNumeracionOut,
    PatronNumeracionUpdate,
)
from app.modules.core.models import Cuenta, Organization
from app.modules.core.numeracion_models import PatronNumeracion, TipoDocumentoNumeracion


async def listar_cuentas(session: AsyncSession) -> list[Cuenta]:
    filas = await session.execute(select(Cuenta).order_by(Cuenta.nombre))
    return list(filas.scalars())


async def obtener_cuenta(session: AsyncSession, cuenta_id: uuid.UUID) -> Cuenta | None:
    return await session.get(Cuenta, cuenta_id)


async def crear_cuenta(session: AsyncSession, datos: CuentaCreate) -> Cuenta:
    cuenta = Cuenta(nombre=datos.nombre)
    session.add(cuenta)
    await session.flush()
    return cuenta


async def actualizar_cuenta(
    session: AsyncSession, cuenta_id: uuid.UUID, datos: CuentaUpdate
) -> Cuenta | None:
    cuenta = await obtener_cuenta(session, cuenta_id)
    if cuenta is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(cuenta, campo, valor)
    await session.flush()
    return cuenta


async def organizaciones_de_cuenta(
    session: AsyncSession, cuenta_id: uuid.UUID
) -> list[Organization]:
    filas = await session.execute(
        select(Organization).where(Organization.cuenta_id == cuenta_id).order_by(Organization.slug)
    )
    return list(filas.scalars())


async def cifs_distintos_de_cuenta(session: AsyncSession, cuenta_id: uuid.UUID) -> bool:
    """Para el aviso (no bloqueo) de la pantalla de numeración: si hay más
    de un CIF entre las organizaciones de la cuenta, compartir secuencia
    entre ellas puede incumplir la correlatividad exigida por separado a
    cada empresa."""
    filas = await session.execute(
        select(Organization.cif)
        .where(Organization.cuenta_id == cuenta_id, Organization.cif.is_not(None))
        .distinct()
    )
    return len(filas.all()) > 1


# --- Patrones de numeración (Fase 16) ---


async def listar_patrones_numeracion(
    session: AsyncSession, cuenta_id: uuid.UUID
) -> list[PatronNumeracionOut]:
    filas = await session.execute(
        select(PatronNumeracion).where(PatronNumeracion.cuenta_id == cuenta_id)
    )
    existentes = {p.tipo_documento: p for p in filas.scalars()}
    return [
        PatronNumeracionOut(
            tipo_documento=tipo.value,
            patron=(existentes[tipo].patron if tipo in existentes else PATRON_POR_DEFECTO[tipo.value]),
            secuencia_compartida=(
                existentes[tipo].secuencia_compartida if tipo in existentes else False
            ),
        )
        for tipo in TipoDocumentoNumeracion
    ]


async def actualizar_patron_numeracion(
    session: AsyncSession, cuenta_id: uuid.UUID, tipo_documento: str, datos: PatronNumeracionUpdate
) -> PatronNumeracionOut:
    if tipo_documento not in {t.value for t in TipoDocumentoNumeracion}:
        raise PatronInvalido(f"Tipo de documento desconocido: '{tipo_documento}'")
    validar_patron(datos.patron)

    fila = await session.scalar(
        select(PatronNumeracion).where(
            PatronNumeracion.cuenta_id == cuenta_id, PatronNumeracion.tipo_documento == tipo_documento
        )
    )
    if fila is None:
        fila = PatronNumeracion(cuenta_id=cuenta_id, tipo_documento=tipo_documento)
        session.add(fila)
    fila.patron = datos.patron
    fila.secuencia_compartida = datos.secuencia_compartida
    await session.flush()
    return PatronNumeracionOut(
        tipo_documento=fila.tipo_documento,
        patron=fila.patron,
        secuencia_compartida=fila.secuencia_compartida,
    )
