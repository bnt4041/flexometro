"""CRM (Fase 29): notas de seguimiento. Mismo criterio de exposición que
`campos_libres` — módulo `always_active`, sin `require_module` ni
`require_permiso` propios: cualquier usuario autenticado de la organización
puede leer y escribir notas, protegido solo por RLS de organización, igual
que los valores de campos libres."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_principal
from app.core.database import get_session
from app.modules.crm import service
from app.modules.crm.models import EntidadNota
from app.modules.crm.schemas import NotaCreate, NotaOut

router = APIRouter(prefix="/api/notas", tags=["crm"], dependencies=[Depends(get_principal)])


@router.get("", response_model=list[NotaOut])
async def listar(
    entidad: EntidadNota,
    entidad_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[NotaOut]:
    notas = await service.listar_notas(session, entidad, entidad_id)
    return [NotaOut.model_validate(n) for n in notas]


@router.post("", response_model=NotaOut, status_code=status.HTTP_201_CREATED)
async def crear(
    entidad: EntidadNota,
    entidad_id: uuid.UUID,
    datos: NotaCreate,
    session: AsyncSession = Depends(get_session),
) -> NotaOut:
    nota = await service.crear_nota(session, entidad, entidad_id, datos)
    return NotaOut.model_validate(nota)


@router.delete("/{nota_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    nota_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await service.eliminar_nota(session, nota_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nota no encontrada")
