import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import permiso_efectivo
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.informes import fuentes, motor
from app.modules.informes.models import Informe

router = APIRouter(
    prefix="/api/informes",
    tags=["informes"],
    dependencies=[Depends(require_module("informes"))],
)


class CampoOut(BaseModel):
    nombre: str
    etiqueta: str
    tipo: str = "texto"
    formato: str = "numero"


class FuenteOut(BaseModel):
    codigo: str
    modulo: str
    etiqueta: str
    descripcion: str
    dimensiones: list[CampoOut]
    metricas: list[CampoOut]


class ConsultaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fuente: str
    dimensiones: list[str] = Field(default_factory=list)
    metricas: list[str] = Field(min_length=1)
    filtros: dict[str, str] = Field(default_factory=dict)


class InformeIn(ConsultaIn):
    nombre: str = Field(min_length=1, max_length=160)
    descripcion: str | None = None
    grafico: str = "tabla"
    compartido: bool = True


class InformeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    descripcion: str | None = None
    fuente: str
    dimensiones: list
    metricas: list
    filtros: dict
    grafico: str
    compartido: bool
    creado_por_nombre: str | None = None


@router.get("/fuentes", response_model=list[FuenteOut])
async def listar_fuentes(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[FuenteOut]:
    """Solo las fuentes que esta persona puede consultar.

    Se filtra por permiso Y por módulo activo: ofrecer «Facturas emitidas» a
    quien no puede ver facturas sería enseñarle la puerta para luego cerrarla
    —o peor, dejarla abierta por descuido—."""
    from app.modules.core.service import active_module_codes

    activos = await active_module_codes(session, principal.organization_id)
    salida = []
    for fuente in fuentes.catalogo():
        if fuente.modulo not in activos:
            continue
        permiso = await permiso_efectivo(session, principal, fuente.modulo)
        if permiso.ver == Alcance.NINGUNO:
            continue
        salida.append(
            FuenteOut(
                codigo=fuente.codigo,
                modulo=fuente.modulo,
                etiqueta=fuente.etiqueta,
                descripcion=fuente.descripcion,
                dimensiones=[
                    CampoOut(nombre=d.nombre, etiqueta=d.etiqueta, tipo=d.tipo)
                    for d in fuente.dimensiones
                ],
                metricas=[
                    CampoOut(nombre=m.nombre, etiqueta=m.etiqueta, formato=m.formato)
                    for m in fuente.metricas
                ],
            )
        )
    return salida


async def _ejecutar(
    session: AsyncSession, principal: Principal, consulta: ConsultaIn
) -> list[dict]:
    fuente = fuentes.obtener(consulta.fuente)
    if fuente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esa fuente no existe")

    # El permiso se resuelve AQUÍ, con quien pide el informe. Un informe
    # guardado por un jefe de obra y abierto por un administrativo se ejecuta
    # con el alcance del administrativo, no con el de quien lo guardó.
    permiso = await permiso_efectivo(session, principal, fuente.modulo)
    if permiso.ver == Alcance.NINGUNO:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Sin permiso de 'ver' en el módulo '{fuente.modulo}'",
        )
    try:
        return await motor.ejecutar(
            session,
            fuente,
            dimensiones=consulta.dimensiones,
            metricas=consulta.metricas,
            filtros=consulta.filtros,
            alcance=permiso.ver,
            subject=principal.subject,
        )
    except motor.InformeInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/consultar")
async def consultar(
    consulta: ConsultaIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    """Ejecuta sin guardar nada: es lo que usa el constructor mientras se
    monta el informe."""
    return {"filas": await _ejecutar(session, principal, consulta)}


@router.get("", response_model=list[InformeOut])
async def listar(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> list[InformeOut]:
    filas = await session.scalars(
        select(Informe)
        .where(
            Informe.organization_id == require_organization_id(),
            # Los no compartidos son solo de quien los hizo: un informe a
            # medias no tiene por qué aparecerle a toda la empresa.
            or_(
                Informe.compartido.is_(True),
                Informe.creado_por_subject == principal.subject,
            ),
        )
        .order_by(Informe.nombre)
    )
    return [InformeOut.model_validate(f) for f in filas]


@router.post("", response_model=InformeOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: InformeIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> InformeOut:
    # Se ejecuta antes de guardar: así no se guarda un informe que no
    # funciona y que fallaría la próxima vez que alguien lo abra.
    await _ejecutar(session, principal, ConsultaIn(**datos.model_dump(include=set(ConsultaIn.model_fields))))
    informe = Informe(
        organization_id=require_organization_id(),
        nombre=datos.nombre,
        descripcion=datos.descripcion,
        fuente=datos.fuente,
        dimensiones=datos.dimensiones,
        metricas=datos.metricas,
        filtros=datos.filtros,
        grafico=datos.grafico,
        compartido=datos.compartido,
        **datos_autoria(),
    )
    session.add(informe)
    await session.flush()
    return InformeOut.model_validate(informe)


@router.get("/{informe_id}/ejecutar")
async def ejecutar_guardado(
    informe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> dict:
    informe = await _informe(session, informe_id, principal)
    consulta = ConsultaIn(
        fuente=informe.fuente,
        dimensiones=informe.dimensiones,
        metricas=informe.metricas,
        filtros=informe.filtros,
    )
    return {
        "informe": InformeOut.model_validate(informe).model_dump(mode="json"),
        "filas": await _ejecutar(session, principal, consulta),
    }


@router.get("/{informe_id}/csv")
async def exportar_csv(
    informe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> StreamingResponse:
    informe = await _informe(session, informe_id, principal)
    filas = await _ejecutar(
        session,
        principal,
        ConsultaIn(
            fuente=informe.fuente,
            dimensiones=informe.dimensiones,
            metricas=informe.metricas,
            filtros=informe.filtros,
        ),
    )
    fuente = fuentes.obtener(informe.fuente)
    columnas = list(informe.dimensiones) + list(informe.metricas)

    def etiqueta_de(nombre: str) -> str:
        if fuente is None:
            return nombre
        campo = next(
            (c for c in (*fuente.dimensiones, *fuente.metricas) if c.nombre == nombre), None
        )
        return campo.etiqueta if campo else nombre

    # Qué métricas son dinero: hay que escribirlas con coma decimal o un Excel
    # español las lee como TEXTO y no se pueden sumar en la hoja.
    dinero = {
        m.nombre for m in (fuente.metricas if fuente else ()) if m.formato == "dinero"
    }

    buffer = io.StringIO()
    # `;` y BOM: es lo que abre bien en un Excel español de doble clic. Con
    # comas, todo acaba en una sola columna.
    escritor = csv.writer(buffer, delimiter=";")
    # Las etiquetas, no los nombres internos: quien abre el CSV es una
    # persona, y «numero» no le dice nada.
    escritor.writerow([etiqueta_de(c) for c in columnas])
    for fila in filas:
        escritor.writerow(
            [
                str(fila.get(c, "")).replace(".", ",") if c in dinero else fila.get(c, "")
                for c in columnas
            ]
        )

    contenido = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([contenido]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{informe.nombre}.csv"'
        },
    )


@router.delete("/{informe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def borrar(
    informe_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> None:
    await session.delete(await _informe(session, informe_id, principal))
    await session.flush()


async def _informe(
    session: AsyncSession, informe_id: uuid.UUID, principal: Principal
) -> Informe:
    informe = await session.scalar(
        select(Informe).where(
            Informe.id == informe_id,
            Informe.organization_id == require_organization_id(),
            or_(
                Informe.compartido.is_(True),
                Informe.creado_por_subject == principal.subject,
            ),
        )
    )
    if informe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return informe
