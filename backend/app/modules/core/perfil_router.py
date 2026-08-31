"""Lo de uno mismo: su perfil y sus favoritos.

Sin `require_permiso` en ninguna ruta, y no es un olvido: son SUS datos. Pedir
permiso de módulo para guardar un favorito o ver en qué grupos estás dejaría
fuera justo a quien menos permisos tiene, que es quien más lo necesita.

Lo que sí acota todo es RLS más el `subject` del token: nadie puede leer ni
escribir los favoritos de otro porque el `subject` no viaja en la petición,
se toma del token.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.tenancy import require_organization_id
from app.modules.core.models import Favorito

# Sin `/api`: este router se monta DENTRO del de `core`, que ya lo lleva.
router = APIRouter(prefix="/yo", tags=["perfil"])


class FavoritoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    etiqueta: str = Field(min_length=1, max_length=120)
    ruta: str = Field(min_length=1, max_length=400)


class FavoritoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    etiqueta: str
    ruta: str
    orden: int


class GrupoDelUsuario(BaseModel):
    id: uuid.UUID
    nombre: str


class PerfilOut(BaseModel):
    subject: str
    username: str
    email: str | None = None
    nombre: str | None = None
    organizacion: str | None = None
    roles: list[str] = []
    grupos: list[GrupoDelUsuario] = []


@router.get("/perfil", response_model=PerfilOut)
async def mi_perfil(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> PerfilOut:
    from app.modules.core.permisos_models import Grupo, GrupoUsuario

    filas = await session.execute(
        select(Grupo.id, Grupo.nombre, GrupoUsuario.usuario_nombre)
        .join(GrupoUsuario, GrupoUsuario.grupo_id == Grupo.id)
        .where(
            Grupo.organization_id == principal.organization_id,
            GrupoUsuario.usuario_subject == principal.subject,
        )
        .order_by(Grupo.nombre)
    )
    grupos, nombre = [], None
    for grupo_id, grupo_nombre, usuario_nombre in filas.all():
        grupos.append(GrupoDelUsuario(id=grupo_id, nombre=grupo_nombre))
        nombre = nombre or usuario_nombre

    email = None
    try:
        from app.core.config import get_settings
        from app.core.keycloak_admin import KeycloakAdmin

        email = await KeycloakAdmin(get_settings()).email_de(principal.subject)
    except Exception:  # noqa: BLE001
        # Sin Keycloak alcanzable se enseña el resto del perfil igual: no
        # poder leer el correo no es motivo para no enseñar nada.
        pass

    return PerfilOut(
        subject=principal.subject,
        username=principal.username,
        email=email,
        nombre=nombre,
        organizacion=principal.organization_slug,
        roles=sorted(principal.roles),
        grupos=grupos,
    )


@router.get("/favoritos", response_model=list[FavoritoOut])
async def listar_favoritos(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> list[FavoritoOut]:
    filas = await session.scalars(
        select(Favorito)
        .where(
            Favorito.organization_id == require_organization_id(),
            Favorito.usuario_subject == principal.subject,
        )
        # Empatados en `orden`, primero el más reciente: lo que acabas de
        # guardar es lo que estabas mirando.
        .order_by(Favorito.orden, Favorito.created_at.desc())
    )
    return [FavoritoOut.model_validate(f) for f in filas]


@router.post("/favoritos", response_model=FavoritoOut, status_code=status.HTTP_201_CREATED)
async def guardar_favorito(
    datos: FavoritoIn,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> FavoritoOut:
    """Guardar la misma ruta dos veces solo cambia la etiqueta: es lo que
    espera quien pulsa la estrella otra vez, no un duplicado."""
    org_id = require_organization_id()
    existente = await session.scalar(
        select(Favorito).where(
            Favorito.organization_id == org_id,
            Favorito.usuario_subject == principal.subject,
            Favorito.ruta == datos.ruta,
        )
    )
    if existente is None:
        existente = Favorito(
            organization_id=org_id,
            usuario_subject=principal.subject,
            etiqueta=datos.etiqueta,
            ruta=datos.ruta,
        )
        session.add(existente)
    else:
        existente.etiqueta = datos.etiqueta
    await session.flush()
    return FavoritoOut.model_validate(existente)


@router.delete("/favoritos/{favorito_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar_favorito(
    favorito_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> None:
    favorito = await session.scalar(
        select(Favorito).where(
            Favorito.id == favorito_id,
            Favorito.organization_id == require_organization_id(),
            # El `subject` va en el filtro, no solo RLS: RLS aísla la
            # organización, no a los compañeros entre sí.
            Favorito.usuario_subject == principal.subject,
        )
    )
    if favorito is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    await session.delete(favorito)
    await session.flush()
