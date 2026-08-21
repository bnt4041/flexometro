import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auditoria import tabla_de
from app.core.auth import Principal, get_principal
from app.core.database import get_session
from app.core.enums import Alcance
from app.core.modules import require_module
from app.core.permisos import require_permiso, verificar_propiedad
from app.core.schemas import Page
from app.modules.presupuestos import formulas, informes
from app.modules.presupuestos import presupuesto_calculo as calc
from app.modules.presupuestos import presupuesto_service as service
from app.modules.presupuestos import service as banco_service
from app.modules.presupuestos import versionado
from app.modules.presupuestos.models_presupuesto import EstadoPresupuesto, Presupuesto
from app.modules.core import auditoria_service
from app.modules.core.auditoria_schemas import RegistroAuditoriaOut
from app.modules.core.tenant_utils import cuenta_id_del_principal
from app.modules.presupuestos.schemas import ConceptoCreate
from app.modules.presupuestos.presupuesto_schemas import (
    AplicarCapituloConComponentesIA,
    AplicarPropuestaIA,
    CambioOut,
    CapituloCreate,
    CapituloUpdate,
    CambioNaturalezaComponente,
    CambioPrecioComponente,
    CambioRendimientoComponente,
    CambioResumenComponente,
    CambioUnidadComponente,
    ComparacionOut,
    ComponenteNuevo,
    ConvertirLinea,
    DescomposicionPartidaOut,
    FormulaMedicionCreate,
    FormulaMedicionOut,
    FormulaMedicionUpdate,
    ProbarFormulaIn,
    ProbarFormulaOut,
    GuardarComoPlantilla,
    LineaDescomposicionOut,
    InstanciarPlantilla,
    LineaMedicionCreate,
    LineaMedicionOut,
    LineaMedicionUpdate,
    LoteLineas,
    PartidaCreate,
    PartidaDetalle,
    PartidaOut,
    PartidaUpdate,
    PegarCapitulos,
    PegarComponentesDescompuesto,
    PegarLineasMedicion,
    PegarPartidas,
    PresupuestoCreate,
    PresupuestoDetalle,
    PresupuestoOut,
    PresupuestoResumen,
    ResultadoPegado,
    PresupuestoUpdate,
    LineaReajusteOut,
    ReajusteIn,
    ReajusteOut,
    RecursosPresupuesto,
    ResultadoCambioPrecio,
    ResultadoSincronizacion,
    VersionOut,
)

guard = Depends(require_module("presupuestos"))

formulas_router = APIRouter(
    prefix="/api/formulas-medicion", tags=["presupuestos"], dependencies=[guard]
)

presupuestos_router = APIRouter(
    prefix="/api/presupuestos", tags=["presupuestos"], dependencies=[guard]
)
capitulos_router = APIRouter(prefix="/api/capitulos", tags=["presupuestos"], dependencies=[guard])
partidas_router = APIRouter(prefix="/api/partidas", tags=["presupuestos"], dependencies=[guard])
mediciones_router = APIRouter(
    prefix="/api/mediciones", tags=["presupuestos"], dependencies=[guard]
)


@presupuestos_router.get("", response_model=Page[PresupuestoResumen])
async def listar(
    q: str | None = None,
    estado: EstadoPresupuesto | None = None,
    es_plantilla: bool = Query(default=False, description="true para listar plantillas"),
    solo_ultima_version: bool = Query(
        default=False, description="Solo la versión más alta de cada línea"
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> Page[PresupuestoResumen]:
    items, total = await service.listar(
        session,
        q=q,
        estado=estado.value if estado else None,
        es_plantilla=es_plantilla,
        solo_ultima_version=solo_ultima_version,
        limit=limit,
        offset=offset,
        creado_por_subject=principal.subject if alcance == Alcance.PROPIOS else None,
    )
    filas = []
    for presupuesto in items:
        pem, importe = await service.total_de(session, presupuesto)
        filas.append(
            PresupuestoResumen(
                **PresupuestoOut.model_validate(presupuesto).model_dump(),
                pem=pem,
                total=importe,
            )
        )
    return Page(items=filas, total=total, limit=limit, offset=offset)


@presupuestos_router.post("", response_model=PresupuestoOut, status_code=status.HTTP_201_CREATED)
async def crear(
    datos: PresupuestoCreate,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    try:
        presupuesto = await service.crear(session, datos)
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return PresupuestoOut.model_validate(presupuesto)


async def _presupuesto_propio(
    session: AsyncSession, presupuesto_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    presupuesto = await service.obtener(session, presupuesto_id)
    if presupuesto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado"
        )
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject)
    return presupuesto


@presupuestos_router.get("/{presupuesto_id}", response_model=PresupuestoDetalle)
async def detalle(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> PresupuestoDetalle:
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    capitulos, totales = await service.arbol_y_totales(session, presupuesto)
    desfasadas = await calc.partidas_desactualizadas(session, presupuesto_id)
    return PresupuestoDetalle(
        **PresupuestoOut.model_validate(presupuesto).model_dump(),
        capitulos=capitulos,
        totales=totales,
        partidas_desactualizadas=len(desfasadas),
    )


@presupuestos_router.get("/{presupuesto_id}/historial", response_model=list[RegistroAuditoriaOut])
async def historial(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[RegistroAuditoriaOut]:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    registros = await auditoria_service.listar_historial(
        session, tabla=tabla_de(Presupuesto), registro_id=presupuesto_id
    )
    return [RegistroAuditoriaOut.model_validate(r) for r in registros]


@presupuestos_router.post(
    "/{presupuesto_id}/aplicar-propuesta-ia", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def aplicar_propuesta_ia(
    presupuesto_id: uuid.UUID,
    datos: AplicarPropuestaIA,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    """Crea el capítulo + partidas que la IA propuso al leer un documento
    (Fase 39/41) en un solo paso, y deja constancia en el historial —
    `Capitulo`/`Partida` no llevan `AutoriaMixin`, así que sin esto su
    creación no dejaría ningún rastro de que fue la IA quien las propuso."""
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    capitulo = await service.crear_capitulo(
        session, presupuesto_id, CapituloCreate(resumen=datos.capitulo_resumen)
    )
    assert capitulo is not None
    for p in datos.partidas:
        await service.crear_partida(
            session,
            capitulo.id,
            PartidaCreate(
                resumen=p.resumen,
                unidad=p.unidad,
                precio=p.precio,
                lineas=[LineaMedicionCreate(uds=p.medicion)],
            ),
        )
    await auditoria_service.registrar_evento(
        session,
        tabla=tabla_de(Presupuesto),
        registro_id=presupuesto_id,
        organization_id=presupuesto.organization_id,
        descripcion=(
            f"La IA añadió el capítulo «{capitulo.resumen}» con "
            f"{len(datos.partidas)} partida{'s' if len(datos.partidas) != 1 else ''}, "
            "leído de un documento."
        ),
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
    )
    await session.commit()
    return {
        "id": str(capitulo.id),
        "resumen": capitulo.resumen,
        "partidas": len(datos.partidas),
    }


@presupuestos_router.post(
    "/{presupuesto_id}/aplicar-capitulo-ia",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def aplicar_capitulo_ia(
    presupuesto_id: uuid.UUID,
    datos: AplicarCapituloConComponentesIA,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    """Como `aplicar_propuesta_ia`, pero para partidas con descompuesto real
    (Fase 42: "Ayuda con IA" proponiendo una fase de obra entera) en vez de
    alzadas — un componente personalizado se da de alta como concepto nuevo
    antes de añadirlo, igual que hacía el cliente a mano en `AyudaIAModal`."""
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    capitulo = await service.crear_capitulo(
        session, presupuesto_id, CapituloCreate(resumen=datos.capitulo_resumen)
    )
    assert capitulo is not None

    for orden, partida_datos in enumerate(datos.partidas):
        if partida_datos.partida_id is not None:
            existente = await service.obtener_partida(session, partida_datos.partida_id)
            # No solo que exista y sea de esta cuenta (ya lo comprobó el
            # asistente al proponerlo): tiene que ser DE ESTE presupuesto —
            # `Partida.presupuesto_id` no se puede cambiar aquí, así que
            # moverla de capítulo sin esta comprobación dejaría una partida
            # con el capítulo de un presupuesto y el presupuesto_id de otro.
            if existente is None or existente.presupuesto_id != presupuesto_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"La partida {partida_datos.partida_id} no es de este presupuesto",
                )
            movida = await service.actualizar_partida(
                session, partida_datos.partida_id, PartidaUpdate(capitulo_id=capitulo.id, orden=orden)
            )
            assert movida is not None
            continue

        partida = await service.crear_partida(
            session,
            capitulo.id,
            PartidaCreate(resumen=partida_datos.resumen, unidad=partida_datos.unidad, orden=orden),
        )
        assert partida is not None
        for comp in partida_datos.componentes:
            if comp.personalizado:
                if not comp.resumen or not comp.unidad or comp.precio is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Un componente personalizado necesita resumen, unidad y precio",
                    )
                concepto = await banco_service.crear_concepto(
                    session,
                    ConceptoCreate(
                        tipo="basico",
                        naturaleza=comp.naturaleza,
                        unidad=comp.unidad,
                        resumen=comp.resumen,
                        precio=comp.precio,
                        origen_precio="manual",
                        origen_dato="ia",
                    ),
                )
                hijo_id = concepto.id
            elif comp.concepto_id is not None:
                hijo_id = comp.concepto_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Cada componente necesita concepto_id o personalizado",
                )
            try:
                await service.anadir_componente(
                    session, partida.id, hijo_id, comp.rendimiento, Decimal("1")
                )
            except service.ConceptoInvalido as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
                ) from exc

    total_partidas = len(datos.partidas)
    movidas = sum(1 for p in datos.partidas if p.partida_id is not None)
    creadas = total_partidas - movidas
    partes_descripcion = []
    if movidas:
        partes_descripcion.append(f"{movidas} partida{'s' if movidas != 1 else ''} movida{'s' if movidas != 1 else ''} aquí")
    if creadas:
        partes_descripcion.append(f"{creadas} partida{'s' if creadas != 1 else ''} nueva{'s' if creadas != 1 else ''}")
    await auditoria_service.registrar_evento(
        session,
        tabla=tabla_de(Presupuesto),
        registro_id=presupuesto_id,
        organization_id=presupuesto.organization_id,
        descripcion=(
            f"La IA creó el capítulo «{capitulo.resumen}» con "
            f"{' y '.join(partes_descripcion)}."
        ),
        usuario_subject=principal.subject,
        usuario_nombre=principal.username,
    )
    await session.commit()
    return {
        "id": str(capitulo.id),
        "resumen": capitulo.resumen,
        "partidas": total_partidas,
    }


@presupuestos_router.patch("/{presupuesto_id}/lineas", response_model=PresupuestoDetalle)
async def actualizar_lineas_en_lote(
    presupuesto_id: uuid.UUID,
    datos: LoteLineas,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoDetalle:
    """Varios cambios de celda de la rejilla en una sola petición (Fase 33).

    Devuelve el presupuesto entero recalculado: la rejilla necesita resincronizar
    los importes y totales, que el servidor rehace por su cuenta.
    """
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    await service.actualizar_lineas_en_lote(session, presupuesto_id, datos.cambios)
    capitulos, totales = await service.arbol_y_totales(session, presupuesto)
    desfasadas = await calc.partidas_desactualizadas(session, presupuesto_id)
    await session.commit()
    return PresupuestoDetalle(
        **PresupuestoOut.model_validate(presupuesto).model_dump(),
        capitulos=capitulos,
        totales=totales,
        partidas_desactualizadas=len(desfasadas),
    )


@presupuestos_router.post("/{presupuesto_id}/reajuste", response_model=ReajusteOut)
async def reajustar(
    presupuesto_id: uuid.UUID,
    datos: ReajusteIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ReajusteOut:
    """Reajusta el presupuesto a un importe o a un margen objetivo (Fase 36).

    Con `aplicar` en falso solo simula, que es lo que alimenta la vista previa.
    """
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        resultado = await service.reajustar(
            session, presupuesto_id, datos.tipo, datos.valor, datos.aplicar
        )
    except service.ReajusteImposible as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presupuesto no encontrado")
    if datos.aplicar:
        # Igual que en el cambio de precio de un componente: se confirma aquí
        # para que la recarga que dispara el cliente al recibir la respuesta ya
        # vea el reajuste (ver `get_session`).
        await session.commit()
    return ReajusteOut(
        **{**resultado, "lineas": [LineaReajusteOut(**linea) for linea in resultado["lineas"]]}
    )


@presupuestos_router.post("/{presupuesto_id}/lineas/{linea_id}/convertir")
async def convertir_linea(
    presupuesto_id: uuid.UUID,
    linea_id: uuid.UUID,
    datos: ConvertirLinea,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict[str, str]:
    """Cambia una línea de capítulo a partida o al revés (Fase 33)."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        resultado = await service.convertir_linea(session, linea_id, datos.tipo)
    except service.ConversionImposible as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    tipo, id_nuevo = resultado
    await session.commit()
    return {"tipo": tipo, "id": str(id_nuevo)}


@presupuestos_router.patch("/{presupuesto_id}", response_model=PresupuestoOut)
async def actualizar(
    presupuesto_id: uuid.UUID,
    datos: PresupuestoUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    presupuesto = await service.actualizar(session, presupuesto_id, datos)
    await session.commit()
    return PresupuestoOut.model_validate(presupuesto)


@presupuestos_router.delete("/{presupuesto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    await service.eliminar(session, presupuesto_id)
    # Sin este commit explícito, el GET de la lista que dispara el cliente en
    # cuanto recibe el 204 puede llegar antes de que `get_session` confirme
    # la transacción (esa confirmación ocurre DESPUÉS de enviar la
    # respuesta) y ver el presupuesto todavía ahí.
    await session.commit()


@presupuestos_router.post(
    "/{presupuesto_id}/sincronizar-precios", response_model=ResultadoSincronizacion
)
async def sincronizar_precios(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoSincronizacion:
    """Trae los precios actuales del cuadro, incluso con los precios
    bloqueados. Es una acción deliberada, nunca automática."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    actualizadas = await calc.sincronizar_precios(session, presupuesto_id)
    await session.commit()
    return ResultadoSincronizacion(partidas_actualizadas=actualizadas)


@presupuestos_router.post(
    "/{presupuesto_id}/capitulos", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def crear_capitulo(
    presupuesto_id: uuid.UUID,
    datos: CapituloCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    capitulo = await service.crear_capitulo(session, presupuesto_id, datos)
    assert capitulo is not None
    await session.commit()
    return {
        "id": str(capitulo.id),
        "codigo": capitulo.codigo,
        "resumen": capitulo.resumen,
        "parent_id": str(capitulo.parent_id) if capitulo.parent_id else None,
    }


@presupuestos_router.post("/{presupuesto_id}/capitulos/pegar", response_model=ResultadoPegado)
async def pegar_capitulos(
    presupuesto_id: uuid.UUID,
    datos: PegarCapitulos,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoPegado:
    """Copia o mueve capítulos enteros —con subcapítulos, partidas,
    descompuestos y mediciones— a este presupuesto (Fase 1e: portapapeles,
    del mismo presupuesto o de otro). `parent_id` los deja a nivel raíz si es
    `None`, o los anida bajo ese capítulo si no."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    pegados = await service.pegar_capitulos(
        session, presupuesto_id, datos.parent_id, datos.capitulo_ids, datos.alcance
    )
    await session.commit()
    return ResultadoPegado(pegadas=pegados)


async def _capitulo_propio(
    session: AsyncSession, capitulo_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    capitulo = await service.obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capítulo no encontrado")
    presupuesto = await service.obtener(session, capitulo.presupuesto_id)
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject if presupuesto else None)
    return capitulo


@capitulos_router.patch("/{capitulo_id}", response_model=dict)
async def actualizar_capitulo(
    capitulo_id: uuid.UUID,
    datos: CapituloUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> dict:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    capitulo = await service.actualizar_capitulo(session, capitulo_id, datos)
    assert capitulo is not None
    await session.commit()
    return {"id": str(capitulo.id), "codigo": capitulo.codigo, "resumen": capitulo.resumen}


@capitulos_router.delete("/{capitulo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_capitulo(
    capitulo_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    await service.eliminar_capitulo(session, capitulo_id)
    # Misma carrera lectura-tras-escritura que en el resto de escrituras de
    # este módulo: sin el commit aquí, el refresco que dispara el cliente al
    # recibir el 204 puede llegar antes de que se confirme el borrado.
    await session.commit()


@capitulos_router.post(
    "/{capitulo_id}/partidas", response_model=PartidaOut, status_code=status.HTTP_201_CREATED
)
async def crear_partida(
    capitulo_id: uuid.UUID,
    datos: PartidaCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PartidaOut:
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    try:
        partida = await service.crear_partida(session, capitulo_id, datos)
    except service.ConceptoInvalido as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except service.PartidaSinDatos as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    assert partida is not None
    # Igual que en `pegar_partidas` más abajo: sin este commit, un cliente que
    # encadene otra escritura justo detrás (añadir un componente a esta
    # partida recién creada, por ejemplo) puede llegar antes de que
    # `get_session` confirme la transacción y encontrarse con un 404.
    await session.commit()
    return PartidaOut.model_validate(partida)


@capitulos_router.post("/{capitulo_id}/partidas/pegar", response_model=ResultadoPegado)
async def pegar_partidas(
    capitulo_id: uuid.UUID,
    datos: PegarPartidas,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoPegado:
    """Copia o mueve partidas enteras —con su descompuesto y sus mediciones—
    a este capítulo (Fase 1b/1c: portapapeles, del mismo presupuesto o de
    otro). Las partidas de origen que ya no existan o no sean de esta
    organización se cuentan como no pegadas en vez de hacer fallar el resto."""
    await _capitulo_propio(session, capitulo_id, alcance, principal)
    pegadas = await service.pegar_partidas(session, capitulo_id, datos.partida_ids, datos.alcance)
    # Se confirma aquí, no se deja al cierre de `get_session`: esa confirmación
    # ocurre DESPUÉS de enviar la respuesta, y el cliente recarga el
    # presupuesto en cuanto la recibe (ver nota de la carrera lectura-tras-
    # escritura en `cambiar_precio_componente`).
    await session.commit()
    return ResultadoPegado(pegadas=pegadas)


async def _partida_propia(
    session: AsyncSession, partida_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    partida = await service.obtener_partida(session, partida_id)
    if partida is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    presupuesto = await service.obtener(session, partida.presupuesto_id)
    verificar_propiedad(alcance, principal, presupuesto.creado_por_subject if presupuesto else None)
    return partida


@partidas_router.get("/{partida_id}", response_model=PartidaDetalle)
async def detalle_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> PartidaDetalle:
    partida = await _partida_propia(session, partida_id, alcance, principal)

    detalle = PartidaDetalle(
        **PartidaOut.model_validate(partida).model_dump(),
        lineas=[LineaMedicionOut.model_validate(l) for l in partida.lineas],
    )
    # Se informa el precio del cuadro solo cuando difiere: es la señal de que
    # el presupuesto está bloqueado y el cuadro se ha movido por debajo.
    if partida.concepto_id is not None:
        from app.modules.presupuestos.service import obtener_concepto

        concepto = await obtener_concepto(session, partida.concepto_id)
        if concepto is not None and concepto.precio != partida.precio:
            detalle.precio_cuadro = concepto.precio
    return detalle


@partidas_router.patch("/{partida_id}", response_model=PartidaOut)
async def actualizar_partida(
    partida_id: uuid.UUID,
    datos: PartidaUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    partida = await service.actualizar_partida(session, partida_id, datos)
    assert partida is not None
    await session.commit()
    return PartidaOut.model_validate(partida)


@partidas_router.delete("/{partida_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _partida_propia(session, partida_id, alcance, principal)
    await service.eliminar_partida(session, partida_id)
    await session.commit()


@partidas_router.post("/{partida_id}/integrar-banco-precios", response_model=PartidaOut)
async def integrar_en_banco_precios(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        partida = await service.integrar_en_banco_precios(session, partida_id)
    except (service.ConceptoYaVinculado, service.CodigoDuplicado) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    assert partida is not None
    await session.commit()
    return PartidaOut.model_validate(partida)


@partidas_router.get("/{partida_id}/descomposicion", response_model=DescomposicionPartidaOut)
async def descomposicion_de_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> DescomposicionPartidaOut:
    """Descompuesto de la partida: el suyo propio si se independizó, y si no el
    del concepto del banco (Fase 34)."""
    await _partida_propia(session, partida_id, alcance, principal)
    resultado = await service.descomposicion_de_partida(session, partida_id)
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    propia, lineas = resultado
    return DescomposicionPartidaOut(
        propia=propia, lineas=[LineaDescomposicionOut(**linea) for linea in lineas]
    )


async def _descomposicion_fresca(session, partida_id: uuid.UUID) -> DescomposicionPartidaOut:
    """Descompuesto ya recalculado, para devolverlo en la misma respuesta de la
    escritura y no depender de una lectura posterior (ver `get_session`)."""
    resultado = await service.descomposicion_de_partida(session, partida_id)
    lineas = [] if resultado is None else resultado[1]
    return DescomposicionPartidaOut(
        propia=bool(resultado and resultado[0]),
        lineas=[LineaDescomposicionOut(**linea) for linea in lineas],
    )


@partidas_router.post(
    "/{partida_id}/descomposicion",
    response_model=DescomposicionPartidaOut,
    status_code=status.HTTP_201_CREATED,
)
async def anadir_componente(
    partida_id: uuid.UUID,
    datos: ComponenteNuevo,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    """Añade un componente al descompuesto de la partida, independizándola del
    banco de precios si aún lo heredaba (Fase 34)."""
    await _partida_propia(session, partida_id, alcance, principal)
    try:
        creado = await service.anadir_componente(
            session, partida_id, datos.hijo_id, datos.rendimiento, datos.factor
        )
    except service.ConceptoInvalido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not creado:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partida no encontrada")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.post(
    "/{partida_id}/descomposicion/independizar", response_model=DescomposicionPartidaOut
)
async def independizar_descomposicion_partida(
    partida_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    """Independiza el descompuesto del banco de precios sin cambiar nada más
    (Fase 1b/1c). Hace falta antes de copiar un componente que la partida
    todavía hereda: el id que se enseña en pantalla para esas líneas es el de
    la fila del banco (`Descomposicion.id`), que no sirve para pegar en otro
    sitio porque no identifica a esta partida."""
    partida = await _partida_propia(session, partida_id, alcance, principal)
    await service.independizar_descomposicion(session, partida)
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.delete(
    "/{partida_id}/descomposicion/{linea_id}", response_model=DescomposicionPartidaOut
)
async def quitar_componente(
    partida_id: uuid.UUID,
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.quitar_componente(session, partida_id, linea_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.patch(
    "/{partida_id}/descomposicion/precio", response_model=ResultadoCambioPrecio
)
async def cambiar_precio_componente(
    partida_id: uuid.UUID,
    datos: CambioPrecioComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoCambioPrecio:
    """Cambia el precio de un componente del descompuesto, en esta partida o en
    todo el presupuesto (Fase 34). Las partidas afectadas se independizan del
    banco de precios; el banco no se modifica."""
    await _partida_propia(session, partida_id, alcance, principal)
    afectadas = await service.cambiar_precio_componente(
        session, partida_id, datos.hijo_id, datos.precio, datos.alcance
    )
    # Se devuelve el descompuesto ya recalculado en vez de dejar que el cliente
    # lo vuelva a pedir: `get_session` confirma la transacción en el cierre de
    # la dependencia, y FastAPI ejecuta eso DESPUÉS de enviar la respuesta, así
    # que un GET inmediato puede leer todavía el estado anterior.
    resultado = await service.descomposicion_de_partida(session, partida_id)
    lineas = [] if resultado is None else resultado[1]
    propia = bool(resultado and resultado[0])
    # Y se confirma aquí mismo, para que cualquier otra lectura que dispare el
    # cliente al recibir la respuesta (recargar el presupuesto, por ejemplo) vea
    # ya el cambio. Ojo al orden: `set_config('app.organization_id', ..., true)`
    # es local a la transacción, así que después del commit ya no se puede leer.
    await session.commit()
    return ResultadoCambioPrecio(
        partidas_afectadas=afectadas,
        descomposicion=DescomposicionPartidaOut(
            propia=propia, lineas=[LineaDescomposicionOut(**l) for l in lineas]
        ),
    )


@partidas_router.patch(
    "/{partida_id}/descomposicion/rendimiento", response_model=DescomposicionPartidaOut
)
async def cambiar_rendimiento_componente(
    partida_id: uuid.UUID,
    datos: CambioRendimientoComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    """Cambia el rendimiento de un componente del descompuesto (siempre "solo
    en esta partida": el rendimiento no se comparte entre partidas, así que no
    hace falta elegir alcance como con el precio)."""
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_rendimiento_componente(
        session, partida_id, datos.hijo_id, datos.rendimiento
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.patch(
    "/{partida_id}/descomposicion/resumen", response_model=DescomposicionPartidaOut
)
async def cambiar_resumen_componente(
    partida_id: uuid.UUID,
    datos: CambioResumenComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    """Cambia el texto de un componente ya en el descompuesto — el concepto
    del banco no se toca, solo la etiqueta que se ve en esta partida."""
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_resumen_componente(
        session, partida_id, datos.hijo_id, datos.resumen
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.patch(
    "/{partida_id}/descomposicion/naturaleza", response_model=DescomposicionPartidaOut
)
async def cambiar_naturaleza_componente(
    partida_id: uuid.UUID,
    datos: CambioNaturalezaComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    """Cambia la clasificación (material/mano de obra/...) de un componente
    ya en el descompuesto, para corregir líneas que se quedaron sin
    clasificar antes de que se pudiera elegir al crearlas."""
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_naturaleza_componente(
        session, partida_id, datos.hijo_id, datos.naturaleza
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.patch(
    "/{partida_id}/descomposicion/unidad", response_model=DescomposicionPartidaOut
)
async def cambiar_unidad_componente(
    partida_id: uuid.UUID,
    datos: CambioUnidadComponente,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> DescomposicionPartidaOut:
    """Cambia la unidad de un componente ya en el descompuesto, para
    corregir por ejemplo una mano de obra dada de alta en "ud" en vez de en
    "h" (y que por eso no contaba en las horas presupuestadas)."""
    await _partida_propia(session, partida_id, alcance, principal)
    if not await service.cambiar_unidad_componente(
        session, partida_id, datos.hijo_id, datos.unidad
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Componente no encontrado")
    salida = await _descomposicion_fresca(session, partida_id)
    await session.commit()
    return salida


@partidas_router.post("/{partida_id}/descomposicion/pegar", response_model=ResultadoPegado)
async def pegar_componentes(
    partida_id: uuid.UUID,
    datos: PegarComponentesDescompuesto,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoPegado:
    """Copia o mueve componentes de un descompuesto a esta partida (Fase
    1b/1c), independizándola del banco de precios si aún lo heredaba."""
    await _partida_propia(session, partida_id, alcance, principal)
    pegadas = await service.pegar_componentes_descompuesto(
        session, partida_id, datos.linea_ids, datos.alcance
    )
    await session.commit()
    return ResultadoPegado(pegadas=pegadas)


@partidas_router.post(
    "/{partida_id}/lineas", response_model=LineaMedicionOut, status_code=status.HTTP_201_CREATED
)
async def crear_linea(
    partida_id: uuid.UUID,
    datos: LineaMedicionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> LineaMedicionOut:
    await _partida_propia(session, partida_id, alcance, principal)
    linea = await service.crear_linea(session, partida_id, datos)
    assert linea is not None
    await session.commit()
    return LineaMedicionOut.model_validate(linea)


@partidas_router.post("/{partida_id}/lineas/pegar", response_model=ResultadoPegado)
async def pegar_lineas(
    partida_id: uuid.UUID,
    datos: PegarLineasMedicion,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> ResultadoPegado:
    """Copia o mueve líneas de medición sueltas a esta partida (Fase 1b/1c)."""
    await _partida_propia(session, partida_id, alcance, principal)
    pegadas = await service.pegar_lineas_medicion(
        session, partida_id, datos.linea_ids, datos.alcance
    )
    await session.commit()
    return ResultadoPegado(pegadas=pegadas)


async def _linea_medicion_propia(
    session: AsyncSession, linea_id: uuid.UUID, alcance: Alcance, principal: Principal
):
    linea = await service.obtener_linea(session, linea_id)
    if linea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Línea no encontrada")
    await _partida_propia(session, linea.partida_id, alcance, principal)
    return linea


@mediciones_router.patch("/{linea_id}", response_model=LineaMedicionOut)
async def actualizar_linea(
    linea_id: uuid.UUID,
    datos: LineaMedicionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> LineaMedicionOut:
    await _linea_medicion_propia(session, linea_id, alcance, principal)
    linea = await service.actualizar_linea(session, linea_id, datos)
    assert linea is not None
    await session.commit()
    return LineaMedicionOut.model_validate(linea)


@mediciones_router.delete("/{linea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_linea(
    linea_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    await _linea_medicion_propia(session, linea_id, alcance, principal)
    await service.eliminar_linea(session, linea_id)
    await session.commit()


# --- Versiones, plantillas e informes ---


@presupuestos_router.get("/{presupuesto_id}/versiones", response_model=list[VersionOut])
async def versiones(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[VersionOut]:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        filas = await versionado.versiones_de(session, presupuesto_id)
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [VersionOut.model_validate(v) for v in filas]


@presupuestos_router.get("/{presupuesto_id}/recursos", response_model=RecursosPresupuesto)
async def recursos(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> RecursosPresupuesto:
    """Materiales y mano de obra agregados de todo el presupuesto — widgets
    "Precios básicos" y "Recursos humanos" (Fase 31)."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    return await service.recursos(session, presupuesto_id)


@presupuestos_router.post(
    "/{presupuesto_id}/nueva-version",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def nueva_version(
    presupuesto_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    """Duplica el presupuesto como versión siguiente, en borrador y con los
    precios sueltos otra vez."""
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        nueva = await versionado.nueva_version(session, presupuesto_id)
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return PresupuestoOut.model_validate(nueva)


@presupuestos_router.get("/{a_id}/comparar/{b_id}", response_model=ComparacionOut)
async def comparar(
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> ComparacionOut:
    await _presupuesto_propio(session, a_id, alcance, principal)
    await _presupuesto_propio(session, b_id, alcance, principal)
    try:
        resultado = await versionado.comparar(session, a_id, b_id)
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    a = await service.obtener(session, a_id)
    b = await service.obtener(session, b_id)
    _, total_a = await service.total_de(session, a)
    _, total_b = await service.total_de(session, b)

    def convertir(cambios) -> list[CambioOut]:
        return [
            CambioOut(
                codigo=c.codigo,
                resumen=c.resumen,
                unidad=c.unidad,
                medicion_a=c.medicion_a,
                medicion_b=c.medicion_b,
                precio_a=c.precio_a,
                precio_b=c.precio_b,
                importe_a=c.importe_a,
                importe_b=c.importe_b,
                delta=c.delta,
            )
            for c in cambios
        ]

    return ComparacionOut(
        a=VersionOut.model_validate(a),
        b=VersionOut.model_validate(b),
        total_a=total_a,
        total_b=total_b,
        delta_total=total_b - total_a,
        altas=convertir(resultado.altas),
        bajas=convertir(resultado.bajas),
        cambios=convertir(resultado.cambios),
        sin_cambios=resultado.sin_cambios,
    )


@presupuestos_router.post(
    "/{presupuesto_id}/guardar-como-plantilla",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def guardar_como_plantilla(
    presupuesto_id: uuid.UUID,
    datos: GuardarComoPlantilla,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    await _presupuesto_propio(session, presupuesto_id, alcance, principal)
    try:
        plantilla = await versionado.guardar_como_plantilla(
            session,
            presupuesto_id,
            nombre=datos.nombre,
            codigo=datos.codigo or await service.siguiente_codigo(session),
            tipo_obra=datos.tipo_obra,
            con_mediciones=datos.con_mediciones,
        )
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return PresupuestoOut.model_validate(plantilla)


@presupuestos_router.post(
    "/{plantilla_id}/instanciar",
    response_model=PresupuestoOut,
    status_code=status.HTTP_201_CREATED,
)
async def instanciar(
    plantilla_id: uuid.UUID,
    datos: InstanciarPlantilla,
    session: AsyncSession = Depends(get_session),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> PresupuestoOut:
    """Crea un presupuesto nuevo con la estructura de la plantilla.

    No se comprueba la propiedad de la plantilla de origen: las plantillas son
    un recurso compartido dentro de la organización, no algo que "propios"
    deba restringir — lo que sí es propio es el presupuesto nuevo que resulta,
    y ese ya nace con la autoría de quien lo instancia.
    """
    try:
        nuevo = await versionado.instanciar_plantilla(
            session,
            plantilla_id,
            nombre=datos.nombre,
            codigo=datos.codigo or await service.siguiente_codigo(session),
            cliente_id=datos.cliente_id,
            emplazamiento=datos.emplazamiento,
        )
    except versionado.PresupuestoNoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return PresupuestoOut.model_validate(nuevo)


@presupuestos_router.get("/{presupuesto_id}/pdf/{documento}")
async def descargar_pdf(
    presupuesto_id: uuid.UUID,
    documento: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> Response:
    """Presupuesto, estado de mediciones o cuadro de precios descompuestos."""
    if documento not in informes.DOCUMENTOS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Documento desconocido. Disponibles: {', '.join(informes.DOCUMENTOS)}",
        )
    presupuesto = await _presupuesto_propio(session, presupuesto_id, alcance, principal)

    pdf = await informes.generar(session, presupuesto, documento)
    nombre = f"{presupuesto.codigo}-{documento}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


router = APIRouter()
router.include_router(presupuestos_router)
router.include_router(capitulos_router)
# --- Fórmulas de medición (Fase 37) ---
#
# Viven a nivel de cuenta, como el diccionario: cualquier usuario del tenant
# puede consultarlas y crearlas desde el propio modal de medición, sin pasar
# por Ajustes.


def _formula_a_out(formula) -> FormulaMedicionOut:
    salida = FormulaMedicionOut.model_validate(formula)
    try:
        salida.variables = formulas.validar(formula.expresion)
    except formulas.FormulaInvalida:
        # Una fórmula guardada que ya no valida (editada a mano en la base de
        # datos) no debe tumbar el listado entero.
        salida.variables = []
    return salida


@formulas_router.get("", response_model=list[FormulaMedicionOut])
async def listar_formulas(
    solo_activas: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> list[FormulaMedicionOut]:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    filas = await service.listar_formulas(session, cuenta_id, solo_activas=solo_activas)
    return [_formula_a_out(f) for f in filas]


@formulas_router.post("", response_model=FormulaMedicionOut, status_code=status.HTTP_201_CREATED)
async def crear_formula(
    datos: FormulaMedicionCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> FormulaMedicionOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        formula = await service.crear_formula(session, cuenta_id, datos)
    except formulas.FormulaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except service.CodigoDuplicado as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return _formula_a_out(formula)


@formulas_router.post("/probar", response_model=ProbarFormulaOut)
async def probar_formula(
    datos: ProbarFormulaIn,
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "ver")),
) -> ProbarFormulaOut:
    """Comprueba una expresión y la calcula con unos valores de prueba, para
    poder ver el resultado antes de guardar la fórmula."""
    try:
        variables = formulas.validar(datos.expresion)
        resultado = formulas.evaluar(datos.expresion, datos.valores)
    except formulas.FormulaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ProbarFormulaOut(variables=variables, resultado=resultado)


@formulas_router.patch("/{formula_id}", response_model=FormulaMedicionOut)
async def actualizar_formula(
    formula_id: uuid.UUID,
    datos: FormulaMedicionUpdate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> FormulaMedicionOut:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    try:
        formula = await service.actualizar_formula(session, cuenta_id, formula_id, datos)
    except formulas.FormulaInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if formula is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fórmula no encontrada")
    await session.commit()
    return _formula_a_out(formula)


@formulas_router.delete("/{formula_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_formula(
    formula_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_principal),
    _alcance: Alcance = Depends(require_permiso("presupuestos", "editar")),
) -> None:
    cuenta_id = await cuenta_id_del_principal(session, principal)
    if not await service.eliminar_formula(session, cuenta_id, formula_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fórmula no encontrada")
    await session.commit()


router.include_router(partidas_router)
router.include_router(mediciones_router)
router.include_router(formulas_router)
