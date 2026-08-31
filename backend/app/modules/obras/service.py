import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redondeo import redondear_precio
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.obras.models import (
    Asignacion,
    Obra,
    ObraPresupuesto,
    ParteTrabajo,
    Personal,
    TipoVinculo,
)
from app.modules.obras.schemas import (
    AsignacionCreate,
    AsignacionUpdate,
    ObraCreate,
    ObraUpdate,
    ParteTrabajoCreate,
    ParteTrabajoUpdate,
    PersonalCreate,
    PersonalUpdate,
)


class CodigoDuplicado(Exception):
    pass


class PresupuestoInvalido(Exception):
    pass


class PersonalInvalido(Exception):
    pass


class CapituloInvalido(Exception):
    pass


async def _siguiente_codigo(session: AsyncSession, modelo, prefijo: str) -> str:
    org_id = require_organization_id()
    patron = re.compile(rf"^{prefijo}(\d+)$")
    codigos = await session.execute(
        select(modelo.codigo).where(modelo.organization_id == org_id)
    )
    maximo = 0
    for (codigo,) in codigos.all():
        encaje = patron.match(codigo)
        if encaje:
            maximo = max(maximo, int(encaje.group(1)))
    return f"{prefijo}{maximo + 1:05d}"


# --- Personal ---


async def siguiente_codigo_personal(session: AsyncSession) -> str:
    return await _siguiente_codigo(session, Personal, "PER")


async def listar_personal(
    session: AsyncSession,
    *,
    activo: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[Personal], int]:
    org_id = require_organization_id()
    base = select(Personal).where(Personal.organization_id == org_id)
    if activo is not None:
        base = base.where(Personal.activo.is_(activo))
    if creado_por_subject is not None:
        base = base.where(Personal.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    filas = await session.execute(base.order_by(Personal.codigo).limit(limit).offset(offset))
    return list(filas.scalars()), int(total or 0)


async def obtener_personal(session: AsyncSession, personal_id: uuid.UUID) -> Personal | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Personal).where(Personal.id == personal_id, Personal.organization_id == org_id)
    )


async def crear_personal(session: AsyncSession, datos: PersonalCreate) -> Personal:
    org_id = require_organization_id()
    codigo = datos.codigo or await siguiente_codigo_personal(session)
    existe = await session.scalar(
        select(Personal.id).where(Personal.organization_id == org_id, Personal.codigo == codigo)
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe personal con el código '{codigo}'")

    persona = Personal(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(persona)
    await session.flush()
    return persona


async def actualizar_personal(
    session: AsyncSession, personal_id: uuid.UUID, datos: PersonalUpdate
) -> Personal | None:
    persona = await obtener_personal(session, personal_id)
    if persona is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(persona, campo, valor)
    await session.flush()
    return persona


async def eliminar_personal(session: AsyncSession, personal_id: uuid.UUID) -> bool:
    persona = await obtener_personal(session, personal_id)
    if persona is None:
        return False
    await session.delete(persona)
    await session.flush()
    return True


# --- Obra ---


async def siguiente_codigo_obra(session: AsyncSession) -> str:
    return await _siguiente_codigo(session, Obra, "OBR")


async def listar_obras(
    session: AsyncSession,
    *,
    estado: str | None = None,
    limit: int = 50,
    offset: int = 0,
    creado_por_subject: str | None = None,
) -> tuple[list[tuple[Obra, str, str]], int]:
    """Devuelve la obra junto con el código y nombre de su presupuesto: el
    listado los muestra sin que el frontend tenga que pedirlos aparte."""
    from app.modules.presupuestos.models_presupuesto import Presupuesto

    org_id = require_organization_id()
    base = (
        select(Obra, Presupuesto.codigo, Presupuesto.nombre)
        .join(Presupuesto, Presupuesto.id == Obra.presupuesto_id)
        .where(Obra.organization_id == org_id)
    )
    if estado:
        base = base.where(Obra.estado == estado)
    if creado_por_subject is not None:
        base = base.where(Obra.creado_por_subject == creado_por_subject)

    total = await session.scalar(
        select(func.count()).select_from(base.with_only_columns(Obra.id).order_by(None).subquery())
    )
    filas = await session.execute(base.order_by(Obra.codigo.desc()).limit(limit).offset(offset))
    return list(filas.all()), int(total or 0)


async def obtener_obra(session: AsyncSession, obra_id: uuid.UUID) -> Obra | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Obra).where(Obra.id == obra_id, Obra.organization_id == org_id)
    )


async def obtener_obra_con_presupuesto(
    session: AsyncSession, obra_id: uuid.UUID
) -> tuple[Obra, str, str] | None:
    from app.modules.presupuestos.models_presupuesto import Presupuesto

    org_id = require_organization_id()
    fila = (
        await session.execute(
            select(Obra, Presupuesto.codigo, Presupuesto.nombre)
            .join(Presupuesto, Presupuesto.id == Obra.presupuesto_id)
            .where(Obra.id == obra_id, Obra.organization_id == org_id)
        )
    ).first()
    return tuple(fila) if fila else None


async def crear_obra(session: AsyncSession, datos: ObraCreate) -> Obra:
    from app.modules.presupuestos.presupuesto_service import obtener as obtener_presupuesto

    org_id = require_organization_id()
    presupuesto = await obtener_presupuesto(session, datos.presupuesto_id)
    if presupuesto is None:
        raise PresupuestoInvalido("El presupuesto no existe en esta organización")

    # Un presupuesto solo se ejecuta en una obra: si ya está vinculado a
    # alguna (como principal o como anexo), no vuelve a entrar.
    ya_ejecutado = await session.scalar(
        select(ObraPresupuesto.id).where(
            ObraPresupuesto.presupuesto_id == datos.presupuesto_id
        )
    )
    if ya_ejecutado:
        raise PresupuestoInvalido("Este presupuesto ya se está ejecutando en una obra")

    codigo = datos.codigo or await siguiente_codigo_obra(session)
    existe = await session.scalar(
        select(Obra.id).where(Obra.organization_id == org_id, Obra.codigo == codigo)
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe una obra con el código '{codigo}'")

    obra = Obra(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(obra)
    await session.flush()

    await vincular_presupuesto(
        session, obra, presupuesto.id, tipo=TipoVinculo.PRINCIPAL
    )
    return obra


async def vincular_presupuesto(
    session: AsyncSession,
    obra: Obra,
    presupuesto_id: uuid.UUID,
    *,
    tipo: TipoVinculo,
    notas: str | None = None,
) -> ObraPresupuesto:
    """Pone un presupuesto en ejecución dentro de esta obra.

    Además de crear el vínculo, **marca el presupuesto como aprobado**: firmar
    la ejecución es exactamente lo que significa aceptarlo, y eso congela sus
    precios (ver `ESTADOS_BLOQUEADOS`). Si ya estaba aprobado no se toca.

    El árbol de la obra se copia aparte, en `arbol_service`: aquí solo se
    establece la relación, para que vincular y copiar se puedan probar por
    separado.
    """
    from app.modules.presupuestos.models_presupuesto import EstadoPresupuesto
    from app.modules.presupuestos.presupuesto_service import obtener as obtener_presupuesto

    org_id = require_organization_id()
    presupuesto = await obtener_presupuesto(session, presupuesto_id)
    if presupuesto is None:
        raise PresupuestoInvalido("El presupuesto no existe en esta organización")

    ya = await session.scalar(
        select(ObraPresupuesto.id).where(
            ObraPresupuesto.presupuesto_id == presupuesto_id
        )
    )
    if ya:
        raise PresupuestoInvalido("Este presupuesto ya se está ejecutando en una obra")

    ultimo = await session.scalar(
        select(func.coalesce(func.max(ObraPresupuesto.orden), -1)).where(
            ObraPresupuesto.obra_id == obra.id
        )
    )
    vinculo = ObraPresupuesto(
        organization_id=org_id,
        obra_id=obra.id,
        presupuesto_id=presupuesto_id,
        tipo=tipo,
        fecha_vinculacion=date.today(),
        orden=(-1 if ultimo is None else ultimo) + 1,
        notas=notas,
    )
    session.add(vinculo)

    if presupuesto.estado != EstadoPresupuesto.APROBADO:
        presupuesto.estado = EstadoPresupuesto.APROBADO
        # Mismo criterio que `presupuesto_service.actualizar`: salir de
        # borrador congela los precios para que la obra no se mueva bajo los
        # pies si cambia el banco.
        presupuesto.precios_bloqueados = True

    await session.flush()

    # Y ahora el árbol. Se hace aquí y no en el router para que no exista
    # ningún camino que vincule un presupuesto sin traerse sus partidas: una
    # obra con el vínculo pero sin árbol no se distingue de un fallo de datos.
    from app.modules.obras import arbol_service

    await arbol_service.copiar_presupuesto(
        session, obra, presupuesto_id, es_anexo=tipo == TipoVinculo.ANEXO
    )
    return vinculo


async def presupuestos_de_obra(
    session: AsyncSession, obra_id: uuid.UUID
) -> list[ObraPresupuesto]:
    return list(
        (
            await session.execute(
                select(ObraPresupuesto)
                .where(ObraPresupuesto.obra_id == obra_id)
                .order_by(ObraPresupuesto.orden)
            )
        ).scalars()
    )


async def desvincular_presupuesto(
    session: AsyncSession, vinculo: ObraPresupuesto
) -> None:
    """Quita un anexo de la obra, y con él las partidas que trajo.

    El principal no se puede quitar: es de donde la obra saca su comparación de
    costes y sus certificaciones.

    Tampoco se quita si ya se ha medido en obra sobre esas partidas. Se podría
    dejar el árbol y borrar solo el vínculo, pero entonces quedarían partidas
    huérfanas indistinguibles de las creadas a mano; y borrarlo todo tiraría
    mediciones reales. Ante las dos malas, se para y se dice por qué.
    """
    from app.modules.obras import arbol_service

    if vinculo.tipo == TipoVinculo.PRINCIPAL:
        raise PresupuestoInvalido(
            "El presupuesto principal no se puede quitar: la obra compara sus costes contra él"
        )
    if await arbol_service.tiene_mediciones_propias(
        session, vinculo.obra_id, vinculo.presupuesto_id
    ):
        raise PresupuestoInvalido(
            "Ya se ha medido en obra sobre las partidas de este anexo: quitarlo "
            "borraría esas mediciones. Elimina primero lo medido si de verdad quieres quitarlo."
        )
    await arbol_service.borrar_copia_de_presupuesto(
        session, vinculo.obra_id, vinculo.presupuesto_id
    )
    await session.delete(vinculo)
    await session.flush()


async def actualizar_obra(
    session: AsyncSession, obra_id: uuid.UUID, datos: ObraUpdate
) -> Obra | None:
    obra = await obtener_obra(session, obra_id)
    if obra is None:
        return None
    cambios = datos.model_dump(exclude_unset=True)
    # `estado_desde` solo se mueve cuando el estado cambia DE VERDAD: guardar
    # la obra con el mismo estado no la «reactiva», y si lo hiciera, una obra
    # parada nunca llegaría a avisar porque cualquier retoque la pondría a
    # cero (ver la vigilancia «obra.estancada»).
    if "estado" in cambios and cambios["estado"] != obra.estado:
        obra.estado_desde = datetime.now(UTC)
    for campo, valor in cambios.items():
        setattr(obra, campo, valor)
    await session.flush()
    return obra


async def eliminar_obra(session: AsyncSession, obra_id: uuid.UUID) -> bool:
    obra = await obtener_obra(session, obra_id)
    if obra is None:
        return False
    await session.delete(obra)
    await session.flush()
    return True


# --- Asignaciones ---


async def listar_asignaciones(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    org_id = require_organization_id()
    filas = await session.execute(
        select(Asignacion, Personal.nombre, Personal.apellidos, Personal.categoria)
        .join(Personal, Personal.id == Asignacion.personal_id)
        .where(Asignacion.obra_id == obra_id, Asignacion.organization_id == org_id)
        .order_by(Asignacion.fecha_desde.desc())
    )
    return [
        {"asignacion": a, "personal_nombre": f"{n} {ap or ''}".strip(), "personal_categoria": c}
        for a, n, ap, c in filas.all()
    ]


async def crear_asignacion(
    session: AsyncSession, obra_id: uuid.UUID, datos: AsignacionCreate
) -> Asignacion | None:
    org_id = require_organization_id()
    obra = await obtener_obra(session, obra_id)
    if obra is None:
        return None

    persona = await obtener_personal(session, datos.personal_id)
    if persona is None:
        raise PersonalInvalido("El trabajador no existe en esta organización")
    if not persona.activo:
        raise PersonalInvalido(f"'{persona.nombre}' está dado de baja")

    asignacion = Asignacion(
        organization_id=org_id,
        obra_id=obra_id,
        personal_id=datos.personal_id,
        coste_hora=datos.coste_hora if datos.coste_hora is not None else persona.coste_hora,
        fecha_desde=datos.fecha_desde,
        fecha_hasta=datos.fecha_hasta,
        notas=datos.notas,
    )
    session.add(asignacion)
    await session.flush()
    return asignacion


async def obtener_asignacion(
    session: AsyncSession, asignacion_id: uuid.UUID
) -> Asignacion | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Asignacion)
        .options(selectinload(Asignacion.partes))
        .where(Asignacion.id == asignacion_id, Asignacion.organization_id == org_id)
    )


async def actualizar_asignacion(
    session: AsyncSession, asignacion_id: uuid.UUID, datos: AsignacionUpdate
) -> Asignacion | None:
    asignacion = await obtener_asignacion(session, asignacion_id)
    if asignacion is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(asignacion, campo, valor)
    await session.flush()
    return asignacion


async def eliminar_asignacion(session: AsyncSession, asignacion_id: uuid.UUID) -> bool:
    asignacion = await obtener_asignacion(session, asignacion_id)
    if asignacion is None:
        return False
    await session.delete(asignacion)
    await session.flush()
    return True


# --- Partes de trabajo ---


async def _validar_capitulo_de_la_obra(
    session: AsyncSession, obra: Obra, capitulo_id: uuid.UUID
) -> None:
    from app.modules.presupuestos.models_presupuesto import Capitulo

    capitulo = await session.scalar(
        select(Capitulo).where(
            Capitulo.id == capitulo_id, Capitulo.presupuesto_id == obra.presupuesto_id
        )
    )
    if capitulo is None:
        raise PresupuestoInvalido(
            "El capítulo indicado no pertenece al presupuesto de esta obra"
        )


async def crear_parte(
    session: AsyncSession, asignacion_id: uuid.UUID, datos: ParteTrabajoCreate
) -> ParteTrabajo | None:
    org_id = require_organization_id()
    asignacion = await obtener_asignacion(session, asignacion_id)
    if asignacion is None:
        return None

    if datos.capitulo_id is not None:
        obra = await obtener_obra(session, asignacion.obra_id)
        await _validar_capitulo_de_la_obra(session, obra, datos.capitulo_id)

    parte = ParteTrabajo(
        organization_id=org_id,
        asignacion_id=asignacion_id,
        fecha=datos.fecha,
        horas=datos.horas,
        capitulo_id=datos.capitulo_id,
        notas=datos.notas,
        coste=redondear_precio(datos.horas * asignacion.coste_hora),
    )
    session.add(parte)
    await session.flush()
    return parte


async def obtener_parte(session: AsyncSession, parte_id: uuid.UUID) -> ParteTrabajo | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(ParteTrabajo)
        .options(selectinload(ParteTrabajo.asignacion))
        .where(ParteTrabajo.id == parte_id, ParteTrabajo.organization_id == org_id)
    )


async def actualizar_parte(
    session: AsyncSession, parte_id: uuid.UUID, datos: ParteTrabajoUpdate
) -> ParteTrabajo | None:
    parte = await obtener_parte(session, parte_id)
    if parte is None:
        return None

    cambios = datos.model_dump(exclude_unset=True)
    if "capitulo_id" in cambios and cambios["capitulo_id"] is not None:
        obra = await obtener_obra(session, parte.asignacion.obra_id)
        await _validar_capitulo_de_la_obra(session, obra, cambios["capitulo_id"])

    for campo, valor in cambios.items():
        setattr(parte, campo, valor)
    if "horas" in cambios:
        parte.coste = redondear_precio(parte.horas * parte.asignacion.coste_hora)
    await session.flush()
    return parte


async def eliminar_parte(session: AsyncSession, parte_id: uuid.UUID) -> bool:
    parte = await obtener_parte(session, parte_id)
    if parte is None:
        return False
    await session.delete(parte)
    await session.flush()
    return True


# --- Agregados de coste de mano de obra (los usa el informe de compras) ---


async def coste_mano_obra_por_capitulo(
    session: AsyncSession, obra_id: uuid.UUID
) -> dict[uuid.UUID | None, Decimal]:
    """Coste real de mano de obra de la obra, agrupado por capítulo.

    La clave `None` agrupa el coste sin capítulo asignado. Vive aquí, en
    `obras`, y lo consume el informe combinado de `compras` — la dependencia
    entre módulos va en esa dirección, nunca al revés.
    """
    org_id = require_organization_id()
    filas = await session.execute(
        select(ParteTrabajo.capitulo_id, func.sum(ParteTrabajo.coste))
        .join(Asignacion, Asignacion.id == ParteTrabajo.asignacion_id)
        .where(Asignacion.obra_id == obra_id, ParteTrabajo.organization_id == org_id)
        .group_by(ParteTrabajo.capitulo_id)
    )
    return {capitulo_id: coste for capitulo_id, coste in filas.all()}
