import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import fijar_organizacion_activa
from app.core.modules import registry
from app.modules.core.admin_schemas import OrganizacionCreate, OrganizacionUpdate
from app.modules.core.cuenta_schemas import EmpresaUpdate
from app.modules.core.models import Organization, OrganizationModule


async def active_module_codes(session: AsyncSession, organization_id: uuid.UUID) -> set[str]:
    rows = await session.execute(
        select(OrganizationModule.module_code).where(
            OrganizationModule.organization_id == organization_id,
            OrganizationModule.is_active.is_(True),
        )
    )
    # Un código guardado de un módulo ya retirado del registro se ignora.
    stored = set(rows.scalars()) & registry.codes()
    # Se devuelve el cierre bajo dependencias, no lo almacenado tal cual: si un
    # módulo gana una dependencia nueva en una versión posterior, sus datos
    # quedarían activos sin la base que necesitan para funcionar.
    # `resolve_activation` añade además los módulos always_active.
    return registry.resolve_activation(stored)


async def is_module_active(
    session: AsyncSession, organization_id: uuid.UUID, code: str
) -> bool:
    spec = registry.get(code)
    if spec.always_active:
        return True
    return code in await active_module_codes(session, organization_id)


async def set_module_active(
    session: AsyncSession, organization_id: uuid.UUID, code: str, active: bool
) -> set[str]:
    """Activa o desactiva un módulo respetando el grafo de dependencias.

    Activar arrastra las dependencias; desactivar exige que nadie activo dependa
    de él. Devuelve el conjunto de módulos activos resultante.
    """
    spec = registry.get(code)
    if spec.always_active and not active:
        raise ValueError(f"El módulo '{code}' es del núcleo y no se puede desactivar")

    current = await active_module_codes(session, organization_id)

    if active:
        target = current | registry.resolve_activation([code])
    else:
        dependents = [
            other.code
            for other in registry.all()
            if code in other.depends_on and other.code in current
        ]
        if dependents:
            raise ValueError(
                f"No se puede desactivar '{code}': dependen de él {', '.join(sorted(dependents))}"
            )
        target = current - {code}

    await _persist(session, organization_id, target)
    return target


async def _persist(
    session: AsyncSession, organization_id: uuid.UUID, target: set[str]
) -> None:
    rows = (
        await session.execute(
            select(OrganizationModule).where(
                OrganizationModule.organization_id == organization_id
            )
        )
    ).scalars()
    existing = {row.module_code: row for row in rows}

    for code in registry.codes():
        should_be_active = code in target
        row = existing.get(code)
        if row is None:
            if should_be_active:
                session.add(
                    OrganizationModule(
                        organization_id=organization_id,
                        module_code=code,
                        is_active=True,
                    )
                )
        elif row.is_active != should_be_active:
            row.is_active = should_be_active

    await session.flush()


# --- Administración de organizaciones (rol superadmin) ---
#
# A diferencia de todo lo demás en la aplicación, estas funciones cruzan la
# frontera de organización a propósito: `Organization` y `OrganizationModule`
# son las únicas tablas del sistema sin RLS (core_0001), precisamente porque
# son ellas las que definen qué es una organización, no datos de negocio de
# una organización concreta.


async def organizaciones_de_mi_cuenta(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[Organization]:
    """Las empresas hermanas (misma cuenta) de la organización dada, ella
    incluida. `core.organization` no lleva RLS —es la tabla que define el
    aislamiento, no una tabla aislada—, así que se filtra a mano por cuenta."""
    mia = await session.get(Organization, organization_id)
    if mia is None:
        return []
    filas = await session.execute(
        select(Organization)
        .where(Organization.cuenta_id == mia.cuenta_id, Organization.is_active.is_(True))
        .order_by(Organization.name)
    )
    return list(filas.scalars())


async def obtener_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> Organization | None:
    return await session.get(Organization, organization_id)


async def slug_organizacion_unico(session: AsyncSession, nombre: str) -> str:
    """Genera el slug del nombre (Fase 41: ya no se teclea a mano en ningún
    sitio) y le añade `-2`, `-3`... si hiciera falta hasta que sea único —
    `Organization.slug` es único en todo el realm, no solo dentro de la
    cuenta."""
    from app.core.texto import slugify

    base = slugify(nombre)
    candidato = base
    sufijo = 2
    while await session.scalar(select(Organization.id).where(Organization.slug == candidato)):
        candidato = f"{base}-{sufijo}"[:64]
        sufijo += 1
    return candidato


async def crear_organizacion(
    session: AsyncSession, cuenta_id: uuid.UUID, datos: OrganizacionCreate
) -> Organization:
    """Una organización siempre nace dentro de una cuenta (Fase 14) — no hay
    alta de organización "suelta"; `cuenta_id` lo exige `cuenta_router.py`
    antes de llamar aquí."""
    slug = await slug_organizacion_unico(session, datos.name)
    organizacion = Organization(cuenta_id=cuenta_id, slug=slug, **datos.model_dump())
    session.add(organizacion)
    await session.flush()

    from app.modules.core import diccionario_seeds

    await diccionario_seeds.sembrar_minimos(session, cuenta_id)

    return organizacion


async def actualizar_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, datos: "OrganizacionUpdate | EmpresaUpdate"
) -> Organization | None:
    organizacion = await obtener_organizacion(session, organization_id)
    if organizacion is None:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(organizacion, campo, valor)
    await session.flush()
    return organizacion


async def subir_logo_organizacion(
    session: AsyncSession, organization_id: uuid.UUID, contenido: bytes, content_type: str
) -> Organization | None:
    """Un único logo por organización: la clave es fija, así que subir uno
    nuevo sencillamente sobrescribe el objeto anterior en MinIO."""
    from app.core import storage

    organizacion = await obtener_organizacion(session, organization_id)
    if organizacion is None:
        return None
    object_key = f"organizacion-logos/{organization_id}"
    await storage.subir_objeto(object_key, contenido, content_type)
    organizacion.logo_object_key = object_key
    organizacion.logo_content_type = content_type
    await session.flush()
    return organizacion


async def eliminar_logo_organizacion(session: AsyncSession, organization_id: uuid.UUID) -> Organization | None:
    from app.core import storage

    organizacion = await obtener_organizacion(session, organization_id)
    if organizacion is None or organizacion.logo_object_key is None:
        return organizacion
    await storage.eliminar_objeto(organizacion.logo_object_key)
    organizacion.logo_object_key = None
    organizacion.logo_content_type = None
    await session.flush()
    return organizacion


async def logo_de_organizacion(
    session: AsyncSession, organization_id: uuid.UUID
) -> tuple[bytes, str] | None:
    from app.core import storage

    organizacion = await obtener_organizacion(session, organization_id)
    if organizacion is None or organizacion.logo_object_key is None:
        return None
    contenido = await storage.descargar_objeto(organizacion.logo_object_key)
    return contenido, organizacion.logo_content_type or "application/octet-stream"


async def estado_modulos(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[dict]:
    """Catálogo completo de módulos con su estado para una organización
    cualquiera, no solo la del principal — es lo que pinta el panel de
    administración al entrar en un tenant.

    `organization_module` lleva RLS (core_0002): sin `fijar_organizacion_activa`
    la sesión seguiría viendo la organización del propio superadmin y esta
    consulta volvería vacía para cualquier otro tenant, no porque no tenga
    módulos activos sino porque la política se lo oculta.
    """
    await fijar_organizacion_activa(session, organization_id)
    activos = await active_module_codes(session, organization_id)
    return [
        {
            "code": spec.code,
            "name": spec.name,
            "depends_on": list(spec.depends_on),
            "always_active": spec.always_active,
            "is_active": spec.code in activos,
        }
        for spec in registry.all()
    ]


async def set_module_active_admin(
    session: AsyncSession, organization_id: uuid.UUID, code: str, active: bool
) -> set[str]:
    """Igual que `set_module_active`, pero para una organización cualquiera.

    Ver `estado_modulos`: sin fijar la organización activa de la sesión, el
    `INSERT`/`UPDATE` sobre `organization_module` incumpliría el `WITH CHECK`
    de su política RLS por pertenecer a una organización distinta de la del
    superadmin conectado.
    """
    await fijar_organizacion_activa(session, organization_id)
    return await set_module_active(session, organization_id, code, active)
