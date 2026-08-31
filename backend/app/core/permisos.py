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


#: Las cuatro acciones, en el orden en que se enseñan en el panel.
ACCIONES = ("ver", "editar", "crear", "borrar")


@dataclass(frozen=True)
class PermisoModulo:
    ver: Alcance
    editar: Alcance
    crear: Alcance
    borrar: Alcance

    def de(self, accion: str) -> Alcance:
        """El alcance de una acción por su nombre. Lanza si la acción no
        existe: un `require_permiso("obras", "modificar")` mal escrito tiene
        que reventar al arrancar, no conceder acceso en silencio."""
        if accion not in ACCIONES:
            raise ValueError(f"Acción desconocida: {accion!r} (son {ACCIONES})")
        return getattr(self, accion)


def _mas_amplio(a: Alcance, b: Alcance) -> Alcance:
    return a if _ORDEN[a] >= _ORDEN[b] else b


async def permiso_efectivo(
    session: AsyncSession, principal: Principal, module_code: str
) -> PermisoModulo:
    return await permiso_de_usuario(
        session,
        organization_id=principal.organization_id,
        subject=principal.subject,
        module_code=module_code,
        es_admin=principal.has_role(ROL_ADMIN_ORGANIZACION),
    )


async def permiso_de_usuario(
    session: AsyncSession,
    *,
    organization_id,
    subject: str,
    module_code: str,
    es_admin: bool = False,
) -> PermisoModulo:
    """Lo mismo que `permiso_efectivo`, pero sin necesitar un `Principal`.

    Hace falta cuando se razona sobre OTRA persona y no sobre quien hace la
    petición: al decidir a quién se le puede avisar de algo, por ejemplo, no
    hay token del que sacar sus roles.
    """
    # Una clave de API no pertenece a ningún grupo: lo que puede hacer sale
    # de sus ámbitos. Se comprueba antes que nada porque `es_admin` es
    # siempre falso para una clave — a propósito, ver `claves.py`.
    if subject.startswith(PREFIJO_CLAVE_API):
        return await _permiso_de_clave(session, subject, module_code)

    if es_admin:
        return PermisoModulo(
            ver=Alcance.TODOS,
            editar=Alcance.TODOS,
            crear=Alcance.TODOS,
            borrar=Alcance.TODOS,
        )

    # Import diferido: evita que `core` (transversal) cree un ciclo de
    # import con módulos que lo llaman desde su propio arranque de router.
    from app.modules.core.permisos_models import Grupo, GrupoPermiso, GrupoUsuario

    filas = await session.execute(
        select(
            GrupoPermiso.ver, GrupoPermiso.editar, GrupoPermiso.crear, GrupoPermiso.borrar
        )
        .join(Grupo, Grupo.id == GrupoPermiso.grupo_id)
        .join(GrupoUsuario, GrupoUsuario.grupo_id == Grupo.id)
        .where(
            Grupo.organization_id == organization_id,
            GrupoUsuario.usuario_subject == subject,
            GrupoPermiso.module_code == module_code,
        )
    )
    # Perteneciendo a varios grupos manda el más amplio de cada acción, por
    # separado: un grupo puede dar «borrar los míos» y otro «editar todos».
    acumulado = dict.fromkeys(ACCIONES, Alcance.NINGUNO)
    for fila in filas.all():
        for accion, valor in zip(ACCIONES, fila, strict=True):
            acumulado[accion] = _mas_amplio(acumulado[accion], valor)
    return PermisoModulo(**acumulado)


#: Los `subject` de las claves de API van marcados para poder distinguirlos
#: de una persona sin consultar nada.
PREFIJO_CLAVE_API = "clave:"


async def _permiso_de_clave(
    session: AsyncSession, subject: str, module_code: str
) -> PermisoModulo:
    """Lo que esa clave puede hacer en ese módulo.

    Cualquier problema (clave borrada, ámbitos con basura) devuelve NINGUNO:
    ante la duda, una integración no puede hacer nada. Fallar abierto aquí
    sería dar acceso total a quien tenga una clave rota.
    """
    import uuid as _uuid

    from app.modules.desarrolladores.models import ClaveApi

    try:
        clave_id = _uuid.UUID(subject.removeprefix(PREFIJO_CLAVE_API))
    except ValueError:
        return PermisoModulo(*(Alcance.NINGUNO,) * 4)

    clave = await session.get(ClaveApi, clave_id)
    if clave is None or not clave.activa:
        return PermisoModulo(*(Alcance.NINGUNO,) * 4)

    ambito = (clave.ambitos or {}).get(module_code) or {}
    valores = {}
    for accion in ACCIONES:
        try:
            valores[accion] = Alcance(ambito.get(accion, Alcance.NINGUNO))
        except ValueError:
            valores[accion] = Alcance.NINGUNO
    return PermisoModulo(**valores)


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
    filtrar por `creado_por_subject` o puede tocar cualquier registro.

    `accion` es una de `ACCIONES`. Un nombre que no esté en la lista revienta
    al construir el router, no en tiempo de petición: es un error de
    programación, y fallar tarde aquí significaría dejar un endpoint sin
    proteger de verdad hasta que alguien lo llame.
    """
    if accion not in ACCIONES:
        raise ValueError(f"Acción desconocida: {accion!r} (son {ACCIONES})")

    async def _guard(
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
    ) -> Alcance:
        permiso = await permiso_efectivo(session, principal, module_code)
        alcance = permiso.de(accion)
        if alcance == Alcance.NINGUNO:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sin permiso de '{accion}' en el módulo '{module_code}'",
            )
        return alcance

    return _guard
