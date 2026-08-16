"""Grupos y sus permisos por módulo.

Todas las funciones reciben `organization_id` explícito en vez de tomarlo del
contexto de la request: las llama tanto el panel de superadmin (sobre
cualquier organización) como el autoservicio del propio tenant (sobre la
suya). Quien llama debe haberse asegurado de que la sesión ve esa
organización — el superadmin con `fijar_organizacion_activa()`, el tenant
porque ya es la suya (ver `permisos_router.py` de cada lado).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import Alcance
from app.core.modules import registry
from app.modules.core.permisos_models import Grupo, GrupoPermiso, GrupoUsuario


class NombreDuplicado(Exception):
    pass


class GrupoNoEncontrado(Exception):
    pass


class MiembroYaEnGrupo(Exception):
    pass


def modulos_disponibles() -> list[str]:
    return sorted(spec.code for spec in registry.all())


async def listar_grupos(session: AsyncSession, organization_id: uuid.UUID) -> list[Grupo]:
    filas = await session.execute(
        select(Grupo)
        .options(selectinload(Grupo.permisos), selectinload(Grupo.miembros))
        .where(Grupo.organization_id == organization_id)
        .order_by(Grupo.nombre)
    )
    return list(filas.scalars().unique())


async def obtener_grupo(session: AsyncSession, grupo_id: uuid.UUID) -> Grupo | None:
    return await session.scalar(
        select(Grupo)
        .options(selectinload(Grupo.permisos), selectinload(Grupo.miembros))
        .where(Grupo.id == grupo_id)
    )


async def crear_grupo(
    session: AsyncSession, organization_id: uuid.UUID, *, nombre: str, descripcion: str | None
) -> Grupo:
    existe = await session.scalar(
        select(Grupo.id).where(Grupo.organization_id == organization_id, Grupo.nombre == nombre)
    )
    if existe:
        raise NombreDuplicado(f"Ya existe un grupo con el nombre '{nombre}' en esta organización")

    grupo = Grupo(organization_id=organization_id, nombre=nombre, descripcion=descripcion)
    session.add(grupo)
    await session.flush()
    # Sin esto, `GrupoDetalle.model_validate` intenta cargar `permisos`/
    # `miembros` fuera del contexto async al serializar la respuesta
    # (MissingGreenlet) — mismo fallo que `listar_facturas` en la Fase 8.
    await session.refresh(grupo, attribute_names=["permisos", "miembros"])
    return grupo


async def actualizar_grupo(
    session: AsyncSession, grupo_id: uuid.UUID, *, nombre: str | None, descripcion: str | None
) -> Grupo | None:
    grupo = await obtener_grupo(session, grupo_id)
    if grupo is None:
        return None
    if nombre is not None:
        grupo.nombre = nombre
    if descripcion is not None:
        grupo.descripcion = descripcion
    await session.flush()
    return grupo


async def eliminar_grupo(session: AsyncSession, grupo_id: uuid.UUID) -> bool:
    grupo = await obtener_grupo(session, grupo_id)
    if grupo is None:
        return False
    await session.delete(grupo)
    await session.flush()
    return True


async def establecer_permisos(
    session: AsyncSession, grupo_id: uuid.UUID, permisos: list[dict]
) -> Grupo | None:
    """Sustituye la lista entera de permisos del grupo — mismo patrón que
    `TarifaModulo` en `billing_service.actualizar_tarifa`: se borra todo y se
    vuelve a crear, más simple que calcular un diff."""
    grupo = await obtener_grupo(session, grupo_id)
    if grupo is None:
        return None

    for permiso in list(grupo.permisos):
        await session.delete(permiso)
    await session.flush()

    for permiso in permisos:
        session.add(
            GrupoPermiso(
                organization_id=grupo.organization_id,
                grupo_id=grupo.id,
                module_code=permiso["module_code"],
                ver=Alcance(permiso["ver"]),
                editar=Alcance(permiso["editar"]),
            )
        )
    await session.flush()
    await session.refresh(grupo, attribute_names=["permisos"])
    return grupo


async def anadir_miembro(
    session: AsyncSession,
    grupo_id: uuid.UUID,
    *,
    usuario_subject: str,
    usuario_nombre: str,
) -> GrupoUsuario:
    grupo = await obtener_grupo(session, grupo_id)
    if grupo is None:
        raise GrupoNoEncontrado("El grupo no existe")

    ya_esta = await session.scalar(
        select(GrupoUsuario.id).where(
            GrupoUsuario.grupo_id == grupo_id, GrupoUsuario.usuario_subject == usuario_subject
        )
    )
    if ya_esta:
        raise MiembroYaEnGrupo("Ese usuario ya pertenece a este grupo")

    miembro = GrupoUsuario(
        organization_id=grupo.organization_id,
        grupo_id=grupo_id,
        usuario_subject=usuario_subject,
        usuario_nombre=usuario_nombre,
    )
    session.add(miembro)
    await session.flush()
    return miembro


async def quitar_miembro(session: AsyncSession, grupo_usuario_id: uuid.UUID) -> bool:
    miembro = await session.get(GrupoUsuario, grupo_usuario_id)
    if miembro is None:
        return False
    await session.delete(miembro)
    await session.flush()
    return True


async def grupos_de_usuario(
    session: AsyncSession, organization_id: uuid.UUID, usuario_subject: str
) -> list[Grupo]:
    filas = await session.execute(
        select(Grupo)
        .join(GrupoUsuario, GrupoUsuario.grupo_id == Grupo.id)
        .options(selectinload(Grupo.permisos))
        .where(Grupo.organization_id == organization_id, GrupoUsuario.usuario_subject == usuario_subject)
    )
    return list(filas.scalars().unique())
