"""Motor de permisos: qué puede ver/editar el usuario actual en un módulo.

Regla de resolución:
1. El rol `admin` de Keycloak (administra su organización) siempre tiene
   TODOS/TODOS en todo — no necesita pertenecer a ningún grupo. Es el mismo
   rol que ya existía desde la Fase 6, no uno nuevo para esto.
2. Si no, se agregan los permisos de TODOS los grupos a los que pertenece el
   usuario en esa organización, y se toma el alcance más amplio de cada uno
   (ver y editar por separado): NINGUNO < PROPIOS < TODOS. Pertenecer a dos
   grupos nunca resta permiso, solo puede sumar.
3. Sin grupos y sin rol `admin`, el alcance es NINGUNO — fallar cerrado,
   mismo principio que las políticas RLS.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance

_ORDEN = {Alcance.NINGUNO: 0, Alcance.PROPIOS: 1, Alcance.TODOS: 2}
ROL_ADMIN_ORGANIZACION = "admin"


@dataclass(frozen=True)
class PermisoModulo:
    ver: Alcance
    editar: Alcance


def _mas_amplio(a: Alcance, b: Alcance) -> Alcance:
    return a if _ORDEN[a] >= _ORDEN[b] else b


async def permiso_efectivo(
    session: AsyncSession, principal: Principal, module_code: str
) -> PermisoModulo:
    if principal.has_role(ROL_ADMIN_ORGANIZACION):
        return PermisoModulo(ver=Alcance.TODOS, editar=Alcance.TODOS)

    # Import diferido: evita que `core` (transversal) cree un ciclo de
    # import con módulos que lo llaman desde su propio arranque de router.
    from app.modules.core.permisos_models import Grupo, GrupoPermiso, GrupoUsuario

    filas = await session.execute(
        select(GrupoPermiso.ver, GrupoPermiso.editar)
        .join(Grupo, Grupo.id == GrupoPermiso.grupo_id)
        .join(GrupoUsuario, GrupoUsuario.grupo_id == Grupo.id)
        .where(
            Grupo.organization_id == principal.organization_id,
            GrupoUsuario.usuario_subject == principal.subject,
            GrupoPermiso.module_code == module_code,
        )
    )
    ver = Alcance.NINGUNO
    editar = Alcance.NINGUNO
    for fila_ver, fila_editar in filas.all():
        ver = _mas_amplio(ver, fila_ver)
        editar = _mas_amplio(editar, fila_editar)
    return PermisoModulo(ver=ver, editar=editar)


def verificar_propiedad(
    alcance: Alcance, principal: Principal, creado_por_subject: str | None
) -> None:
    """Para detalle/editar/borrar de un registro concreto: con alcance PROPIOS,
    quien no lo creó no puede ni saber que existe — 404, no 403, mismo
    principio de "fallar cerrado" que RLS aplica a otra organización. Los
    registros históricos sin `creado_por_subject` (anteriores a la Fase 12)
    quedan invisibles bajo PROPIOS: es el comportamiento esperado, no un bug.
    """
    if alcance == Alcance.PROPIOS and creado_por_subject != principal.subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")


def require_permiso(module_code: str, accion: str):
    """Dependencia de router: 403 si el alcance es NINGUNO, y devuelve el
    alcance concedido (PROPIOS/TODOS) para que el endpoint sepa si tiene que
    filtrar por `creado_por_subject` o puede ver/editar cualquier registro.
    `accion` es 'ver' o 'editar'.
    """

    async def _guard(
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
    ) -> Alcance:
        permiso = await permiso_efectivo(session, principal, module_code)
        alcance = permiso.ver if accion == "ver" else permiso.editar
        if alcance == Alcance.NINGUNO:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sin permiso de '{accion}' en el módulo '{module_code}'",
            )
        return alcance

    return _guard
