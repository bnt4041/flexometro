import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.numeracion import PATRON_POR_DEFECTO, PatronInvalido, validar_patron
from app.modules.core.cuenta_schemas import (
    CuentaCreate,
    CuentaUpdate,
    EmpresaCrear,
    PatronNumeracionOut,
    PatronNumeracionUpdate,
)
from app.modules.core.models import Cuenta, Organization
from app.modules.core.numeracion_models import PatronNumeracion, TipoDocumentoNumeracion


class LimiteEmpresasSuperado(Exception):
    pass


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


# --- Empresas de la cuenta (Fase 41) ---


async def crear_empresa_autoservicio(
    session: AsyncSession, cuenta_id: uuid.UUID, datos: EmpresaCrear
) -> Organization:
    """Como `core_service.crear_organizacion`, pero comprobando antes el
    límite de empresas de la cuenta — la única diferencia real entre este
    camino (autoservicio) y el del superadmin."""
    from app.modules.core import service as core_service
    from app.modules.core.admin_schemas import OrganizacionCreate

    cuenta = await obtener_cuenta(session, cuenta_id)
    if cuenta is None:
        raise ValueError("Cuenta no encontrada")

    actuales = await organizaciones_de_cuenta(session, cuenta_id)
    if len(actuales) >= cuenta.max_organizaciones:
        raise LimiteEmpresasSuperado(
            f"Esta cuenta ya tiene {len(actuales)} de {cuenta.max_organizaciones} empresas permitidas"
        )

    return await core_service.crear_organizacion(
        session, cuenta_id, OrganizacionCreate(name=datos.name, cif=datos.cif)
    )


async def empresa_de_cuenta(
    session: AsyncSession, cuenta_id: uuid.UUID, organization_id: uuid.UUID
) -> Organization | None:
    """Una organización concreta, solo si es de esta cuenta — para que un
    admin de organización pueda leer/editar cualquier empresa suya (Fase 41,
    pestañas de Ajustes -> Empresa) sin poder tocar una de otra cuenta."""
    return await session.scalar(
        select(Organization).where(
            Organization.id == organization_id, Organization.cuenta_id == cuenta_id
        )
    )


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
