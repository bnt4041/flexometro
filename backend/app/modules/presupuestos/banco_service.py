"""El banco de precios como árbol (Fase 50).

Hasta ahora el banco era una lista plana que se ordenaba por `tipo, codigo`.
Aquí se le da la misma estructura que a un presupuesto —capítulos que
cuelgan de capítulos, y fichas que cuelgan de un capítulo— para poder
trabajarlo con la misma rejilla.

Ojo a la distinción, que es deliberada y se repite en todo el módulo:
`capitulo_id` dice DÓNDE está la ficha (estructura, se mueve arrastrando) y
`familia_id` dice QUÉ es (clasificación, se asigna en masa). No son lo
mismo y ninguna implica la otra.
"""

import re
import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import datos_autoria, require_organization_id
from app.core.visibilidad import organizaciones_visibles
from app.modules.presupuestos.models import CapituloBanco, Concepto, Descomposicion
from app.modules.presupuestos.schemas import (
    ArbolBanco,
    PaginaFichas,
    CapituloBancoCreate,
    CapituloBancoOut,
    CapituloBancoUpdate,
    ConceptoEnBanco,
)

PREFIJO_CAPITULO = "C"


class CodigoDuplicado(Exception):
    pass


class CapituloConContenido(Exception):
    pass


class CicloDeCapitulos(Exception):
    pass


async def siguiente_codigo_capitulo(session: AsyncSession) -> str:
    """Correlativo simple (C00001, C00002…). No refleja la jerarquía a
    propósito: un capítulo se puede mover de sitio, y renumerar la rama
    entera en cada arrastre invalidaría códigos que el usuario ya conoce."""
    org_id = require_organization_id()
    patron = re.compile(rf"^{PREFIJO_CAPITULO}(\d+)$")
    codigos = await session.execute(
        select(CapituloBanco.codigo).where(CapituloBanco.organization_id == org_id)
    )
    maximo = 0
    for (codigo,) in codigos.all():
        encaje = patron.match(codigo)
        if encaje:
            maximo = max(maximo, int(encaje.group(1)))
    return f"{PREFIJO_CAPITULO}{maximo + 1:05d}"


async def arbol(session: AsyncSession) -> ArbolBanco:
    """El esqueleto del banco: capítulos (que son pocos) y cuántas fichas
    cuelgan de cada uno. Las fichas se piden aparte con `fichas()`.

    Se separó así al comprobar que un banco importado de verdad trae más de
    12.000 fichas: devolverlas aquí eran 6 MB por respuesta y otras tantas
    filas en el DOM. El recuento permite pintar el árbol y decir "este
    capítulo tiene 340 fichas" sin traerse ninguna."""
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)

    capitulos = list(
        (
            await session.execute(
                select(CapituloBanco)
                .where(CapituloBanco.organization_id.in_(ids_visibles))
                .order_by(CapituloBanco.orden, CapituloBanco.codigo)
            )
        ).scalars()
    )

    conteos = (
        await session.execute(
            select(Concepto.capitulo_id, func.count())
            .where(Concepto.organization_id.in_(ids_visibles))
            .group_by(Concepto.capitulo_id)
        )
    ).all()
    # La raíz (sin capítulo) va bajo la clave vacía: JSON no admite null como
    # clave de objeto.
    por_capitulo = {(str(cap_id) if cap_id else ""): int(n) for cap_id, n in conteos}

    return ArbolBanco(
        capitulos=[CapituloBancoOut.model_validate(c) for c in capitulos],
        fichas_por_capitulo=por_capitulo,
        total_fichas=sum(por_capitulo.values()),
    )


async def fichas(
    session: AsyncSession,
    *,
    capitulo_id: uuid.UUID | None = None,
    sin_capitulo: bool = False,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> PaginaFichas:
    """Las fichas de UN capítulo (o las sueltas, o las que coincidan con una
    búsqueda), paginadas. Con `q` se busca en todo el banco sin importar el
    capítulo: es como se encuentra algo en un banco de 12.000 fichas."""
    org_id = require_organization_id()
    ids_visibles = await organizaciones_visibles(session, org_id)

    base = select(Concepto).where(Concepto.organization_id.in_(ids_visibles))
    if q:
        patron = f"%{q}%"
        base = base.where(
            or_(Concepto.resumen.ilike(patron), Concepto.codigo.ilike(patron))
        )
    elif sin_capitulo:
        base = base.where(Concepto.capitulo_id.is_(None))
    elif capitulo_id is not None:
        base = base.where(Concepto.capitulo_id == capitulo_id)

    total = await session.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    )
    filas = list(
        (
            await session.execute(
                base.order_by(Concepto.orden, Concepto.codigo).limit(limit).offset(offset)
            )
        ).scalars()
    )

    con_desglose: set[uuid.UUID] = set()
    if filas:
        con_desglose = set(
            (
                await session.execute(
                    select(Descomposicion.padre_id)
                    .where(Descomposicion.padre_id.in_([f.id for f in filas]))
                    .group_by(Descomposicion.padre_id)
                )
            ).scalars()
        )

    return PaginaFichas(
        items=[_a_ficha(c, c.id in con_desglose) for c in filas],
        total=int(total or 0),
    )


def _a_ficha(c: Concepto, tiene_descompuesto: bool) -> ConceptoEnBanco:
    return ConceptoEnBanco(
        **{
            campo: getattr(c, campo)
            for campo in (
                "id", "codigo", "tipo", "naturaleza", "unidad", "resumen",
                "texto", "precio", "precio_venta", "origen_precio",
                "familia_id", "capitulo_id", "orden", "activo",
            )
        },
        tiene_descompuesto=tiene_descompuesto,
    )


async def obtener_capitulo(
    session: AsyncSession, capitulo_id: uuid.UUID
) -> CapituloBanco | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(CapituloBanco).where(
            CapituloBanco.id == capitulo_id, CapituloBanco.organization_id == org_id
        )
    )


async def crear_capitulo(session: AsyncSession, datos: CapituloBancoCreate) -> CapituloBanco:
    org_id = require_organization_id()
    valores = datos.model_dump()
    codigo = valores.pop("codigo", None) or await siguiente_codigo_capitulo(session)

    existe = await session.scalar(
        select(CapituloBanco.id).where(
            CapituloBanco.organization_id == org_id, CapituloBanco.codigo == codigo
        )
    )
    if existe:
        raise CodigoDuplicado(f"Ya existe un capítulo con el código '{codigo}'")

    capitulo = CapituloBanco(
        organization_id=org_id, codigo=codigo, **valores, **datos_autoria()
    )
    session.add(capitulo)
    await session.flush()
    return capitulo


async def _seria_ciclo(
    session: AsyncSession, capitulo_id: uuid.UUID, nuevo_padre_id: uuid.UUID
) -> bool:
    """¿Colgar `capitulo_id` de `nuevo_padre_id` lo metería dentro de sí
    mismo? Se sube por la cadena de padres del destino buscando el propio
    capítulo. Con guarda de vueltas por si la tabla ya tuviera un ciclo."""
    if capitulo_id == nuevo_padre_id:
        return True
    actual: uuid.UUID | None = nuevo_padre_id
    vistos: set[uuid.UUID] = set()
    while actual is not None and actual not in vistos:
        vistos.add(actual)
        padre = await session.scalar(
            select(CapituloBanco.parent_id).where(CapituloBanco.id == actual)
        )
        if padre == capitulo_id:
            return True
        actual = padre
    return False


async def actualizar_capitulo(
    session: AsyncSession, capitulo_id: uuid.UUID, datos: CapituloBancoUpdate
) -> CapituloBanco | None:
    capitulo = await obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        return None

    cambios = datos.model_dump(exclude_unset=True)
    nuevo_padre = cambios.get("parent_id")
    if nuevo_padre is not None and await _seria_ciclo(session, capitulo_id, nuevo_padre):
        raise CicloDeCapitulos("Un capítulo no puede colgar de sí mismo ni de un descendiente")

    for campo, valor in cambios.items():
        setattr(capitulo, campo, valor)
    await session.flush()
    return capitulo


async def eliminar_capitulo(session: AsyncSession, capitulo_id: uuid.UUID) -> bool:
    """Solo si está vacío. Las fichas no se borran nunca en cascada: valen
    mucho más que el capítulo que las agrupa, y el FK es SET NULL — pero
    dejar que un borrado suelte en la raíz 200 fichas sin avisar sería una
    sorpresa desagradable, así que se exige vaciarlo antes."""
    capitulo = await obtener_capitulo(session, capitulo_id)
    if capitulo is None:
        return False

    hijos = await session.scalar(
        select(func.count())
        .select_from(CapituloBanco)
        .where(CapituloBanco.parent_id == capitulo_id)
    )
    fichas = await session.scalar(
        select(func.count()).select_from(Concepto).where(Concepto.capitulo_id == capitulo_id)
    )
    if hijos or fichas:
        raise CapituloConContenido(
            "El capítulo no está vacío: saca antes sus fichas y subcapítulos"
        )

    await session.delete(capitulo)
    await session.flush()
    return True


async def asignar_familia(
    session: AsyncSession, concepto_ids: list[uuid.UUID], familia_id: uuid.UUID | None
) -> int:
    """Clasificación en masa. Devuelve cuántas fichas se han tocado — puede
    ser menos que las pedidas si alguna es de otra organización, y en ese
    caso simplemente no se cambia (RLS ya la hace invisible)."""
    return await _actualizar_muchos(session, concepto_ids, {"familia_id": familia_id})


async def mover_al_capitulo(
    session: AsyncSession, concepto_ids: list[uuid.UUID], capitulo_id: uuid.UUID | None
) -> int:
    """Mover fichas de sitio en el árbol. `capitulo_id` nulo las devuelve a
    la raíz del banco."""
    if capitulo_id is not None and await obtener_capitulo(session, capitulo_id) is None:
        raise CapituloConContenido("El capítulo de destino no existe en esta organización")
    return await _actualizar_muchos(session, concepto_ids, {"capitulo_id": capitulo_id})


async def previsualizar_por_naturaleza(
    session: AsyncSession, naturaleza: str, *, limite_muestra: int = 20
) -> tuple[int, list[Concepto]]:
    """Cuántas fichas hay de una naturaleza y una muestra de ellas — para que
    la IA (Fase 50) pueda enseñar una propuesta legible sin tener que
    enumerar miles de ids: "por naturaleza" no busca por texto, es un campo
    ya guardado en cada ficha, así que aquí no hace falta ningún límite de
    búsqueda para saber CUÁNTAS hay, solo para la muestra que se enseña."""
    org_id = require_organization_id()
    condiciones = (Concepto.organization_id == org_id, Concepto.naturaleza == naturaleza)
    total = await session.scalar(
        select(func.count()).select_from(Concepto).where(*condiciones)
    )
    muestra = list(
        (
            await session.execute(
                select(Concepto).where(*condiciones).order_by(Concepto.codigo).limit(limite_muestra)
            )
        ).scalars()
    )
    return int(total or 0), muestra


async def mover_por_naturaleza(
    session: AsyncSession, naturaleza: str, capitulo_id: uuid.UUID | None
) -> int:
    """Mueve TODAS las fichas de una naturaleza al capítulo, de una sentencia
    — sin cargar cada fila en Python: puede ser media plantilla del banco.
    Mismo motivo que `previsualizar_por_naturaleza`: es un filtro exacto
    sobre un campo ya guardado, no una búsqueda con límite."""
    org_id = require_organization_id()
    if capitulo_id is not None and await obtener_capitulo(session, capitulo_id) is None:
        raise CapituloConContenido("El capítulo de destino no existe en esta organización")
    resultado = await session.execute(
        update(Concepto)
        .where(Concepto.organization_id == org_id, Concepto.naturaleza == naturaleza)
        .values(capitulo_id=capitulo_id)
    )
    await session.flush()
    return resultado.rowcount or 0


async def _actualizar_muchos(
    session: AsyncSession, concepto_ids: list[uuid.UUID], valores: dict
) -> int:
    org_id = require_organization_id()
    filas = list(
        (
            await session.execute(
                select(Concepto).where(
                    Concepto.id.in_(concepto_ids), Concepto.organization_id == org_id
                )
            )
        ).scalars()
    )
    for fila in filas:
        for campo, valor in valores.items():
            setattr(fila, campo, valor)
    await session.flush()
    return len(filas)
