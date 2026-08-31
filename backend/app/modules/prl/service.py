"""Lógica del módulo PRL: recursos, catálogo y documentos con caducidad.

El circuito de firma vive aparte, en `firma.py` — tiene su propio espacio sin
sesión y bastante más delicadeza.
"""

import re
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import datos_autoria, require_organization_id
from app.modules.prl.models import (
    AmbitoPRL,
    DocumentoPRL,
    PlantillaDocumento,
    Recurso,
    TipoDocumentoPRL,
)
from app.modules.prl.schemas import (
    DocumentoPRLCreate,
    DocumentoPRLOut,
    DocumentoPRLUpdate,
    EstadoVigencia,
    PlantillaDocumentoCreate,
    PlantillaDocumentoUpdate,
    RecursoCreate,
    RecursoUpdate,
    ResumenVigencia,
    TipoDocumentoPRLCreate,
    TipoDocumentoPRLUpdate,
    estado_de,
)


class CodigoDuplicado(Exception):
    pass


class TipoInvalido(Exception):
    pass


class EntidadInvalida(Exception):
    pass


def _slug(texto: str, maximo: int = 40) -> str:
    """Código legible a partir del nombre, para el catálogo y las plantillas:
    en un catálogo un `TIPO-00007` no dice nada, y `reconocimiento-medico` sí."""
    limpio = re.sub(r"[^a-z0-9]+", "-", texto.lower().strip())
    return limpio.strip("-")[:maximo] or "sin-nombre"


async def _codigo_libre(
    session: AsyncSession, modelo, base: str, org_id: uuid.UUID
) -> str:
    """`base`, o `base-2`, `base-3`... hasta encontrar uno sin usar."""
    candidato = base
    for intento in range(2, 100):
        existe = await session.scalar(
            select(modelo.id).where(modelo.organization_id == org_id, modelo.codigo == candidato)
        )
        if existe is None:
            return candidato
        candidato = f"{base[:36]}-{intento}"
    raise CodigoDuplicado(f"No se ha podido generar un código libre a partir de «{base}»")


# ── Recursos ────────────────────────────────────────────────────────────


async def siguiente_codigo_recurso(session: AsyncSession) -> str:
    org_id = require_organization_id()

    async def existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(Recurso.id).where(Recurso.organization_id == org_id, Recurso.codigo == codigo)
            )
        ) is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento="recurso", existe=existe
    )


async def _validar_destinos(
    session: AsyncSession, obra_id: uuid.UUID | None, responsable_id: uuid.UUID | None
) -> None:
    org_id = require_organization_id()
    if obra_id is not None:
        from app.modules.obras.models import Obra

        if await session.scalar(
            select(Obra.id).where(Obra.id == obra_id, Obra.organization_id == org_id)
        ) is None:
            raise EntidadInvalida("La obra indicada no existe en esta organización")
    if responsable_id is not None:
        from app.modules.obras.models import Personal

        if await session.scalar(
            select(Personal.id).where(
                Personal.id == responsable_id, Personal.organization_id == org_id
            )
        ) is None:
            raise EntidadInvalida("El responsable indicado no existe en esta organización")


async def crear_recurso(session: AsyncSession, datos: RecursoCreate) -> Recurso:
    org_id = require_organization_id()
    await _validar_destinos(session, datos.obra_id, datos.responsable_id)
    codigo = datos.codigo or await siguiente_codigo_recurso(session)
    if await session.scalar(
        select(Recurso.id).where(Recurso.organization_id == org_id, Recurso.codigo == codigo)
    ):
        raise CodigoDuplicado(f"Ya existe un recurso con el código {codigo}")

    recurso = Recurso(
        organization_id=org_id,
        codigo=codigo,
        **datos.model_dump(exclude={"codigo"}),
        **datos_autoria(),
    )
    session.add(recurso)
    await session.flush()
    return recurso


async def actualizar_recurso(
    session: AsyncSession, recurso: Recurso, datos: RecursoUpdate
) -> Recurso:
    cambios = datos.model_dump(exclude_unset=True)
    if "obra_id" in cambios or "responsable_id" in cambios:
        await _validar_destinos(
            session,
            cambios.get("obra_id", recurso.obra_id),
            cambios.get("responsable_id", recurso.responsable_id),
        )
    for campo, valor in cambios.items():
        setattr(recurso, campo, valor)
    await session.flush()
    return recurso


async def obtener_recurso(session: AsyncSession, recurso_id: uuid.UUID) -> Recurso | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(Recurso).where(Recurso.id == recurso_id, Recurso.organization_id == org_id)
    )


async def listar_recursos(
    session: AsyncSession,
    *,
    tipo: str | None = None,
    obra_id: uuid.UUID | None = None,
    solo_activos: bool = False,
    busqueda: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Recurso], int]:
    org_id = require_organization_id()
    filtros = [Recurso.organization_id == org_id]
    if tipo:
        filtros.append(Recurso.tipo == tipo)
    if obra_id:
        filtros.append(Recurso.obra_id == obra_id)
    if solo_activos:
        filtros.append(Recurso.activo.is_(True))
    if busqueda:
        patron = f"%{busqueda.lower()}%"
        filtros.append(
            func.lower(Recurso.nombre).like(patron)
            | func.lower(func.coalesce(Recurso.matricula, "")).like(patron)
            | func.lower(Recurso.codigo).like(patron)
        )

    total = await session.scalar(select(func.count()).select_from(Recurso).where(*filtros)) or 0
    filas = await session.scalars(
        select(Recurso).where(*filtros).order_by(Recurso.codigo).limit(limit).offset(offset)
    )
    return list(filas), total


# ── Catálogo de tipos ───────────────────────────────────────────────────


async def crear_tipo(session: AsyncSession, datos: TipoDocumentoPRLCreate) -> TipoDocumentoPRL:
    org_id = require_organization_id()
    base = datos.codigo or _slug(datos.nombre)
    codigo = await _codigo_libre(session, TipoDocumentoPRL, base, org_id)
    tipo = TipoDocumentoPRL(
        organization_id=org_id, codigo=codigo, **datos.model_dump(exclude={"codigo"})
    )
    session.add(tipo)
    await session.flush()
    return tipo


async def actualizar_tipo(
    session: AsyncSession, tipo: TipoDocumentoPRL, datos: TipoDocumentoPRLUpdate
) -> TipoDocumentoPRL:
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(tipo, campo, valor)
    await session.flush()
    return tipo


async def obtener_tipo(session: AsyncSession, tipo_id: uuid.UUID) -> TipoDocumentoPRL | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(TipoDocumentoPRL).where(
            TipoDocumentoPRL.id == tipo_id, TipoDocumentoPRL.organization_id == org_id
        )
    )


async def listar_tipos(
    session: AsyncSession, *, ambito: str | None = None, solo_activos: bool = True
) -> list[TipoDocumentoPRL]:
    org_id = require_organization_id()
    filtros = [TipoDocumentoPRL.organization_id == org_id]
    if ambito:
        filtros.append(TipoDocumentoPRL.ambito == ambito)
    if solo_activos:
        filtros.append(TipoDocumentoPRL.activo.is_(True))
    filas = await session.scalars(
        select(TipoDocumentoPRL).where(*filtros).order_by(TipoDocumentoPRL.ambito, TipoDocumentoPRL.nombre)
    )
    return list(filas)


# ── Documentos PRL ──────────────────────────────────────────────────────


def caducidad_sugerida(emision: date | None, meses_validez: int) -> date:
    """Propuesta de caducidad = emisión + validez del tipo. Solo es un
    valor por defecto para el formulario; manda siempre lo que ponga el
    papel."""
    base = emision or date.today()
    if meses_validez <= 0:
        # «No caduca» no existe en este módulo (ver el modelo): se traduce a
        # una fecha muy lejana para que la fila siga entrando en las mismas
        # consultas de vigencia sin casos especiales.
        return base.replace(year=base.year + 99)
    anios, meses = divmod(meses_validez, 12)
    mes_final = base.month + meses
    anio_final = base.year + anios + (mes_final - 1) // 12
    mes_final = (mes_final - 1) % 12 + 1
    # Recorta el día si el mes destino es más corto (31 de enero + 1 mes).
    dia = min(base.day, [31, 29 if anio_final % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes_final - 1])
    return date(anio_final, mes_final, dia)


async def crear_documento(session: AsyncSession, datos: DocumentoPRLCreate) -> DocumentoPRL:
    org_id = require_organization_id()
    tipo = await obtener_tipo(session, datos.tipo_id)
    if tipo is None:
        raise TipoInvalido("El tipo de documento no existe en esta organización")
    if tipo.ambito != datos.ambito:
        raise TipoInvalido(
            f"El tipo «{tipo.nombre}» es del ámbito {tipo.ambito}, no de {datos.ambito}"
        )
    if datos.ambito != AmbitoPRL.EMPRESA and datos.entidad_id is None:
        raise EntidadInvalida(f"Un documento de ámbito {datos.ambito} necesita una entidad")

    documento = DocumentoPRL(
        organization_id=org_id, **datos.model_dump(), **datos_autoria()
    )
    session.add(documento)
    await session.flush()
    return documento


async def actualizar_documento(
    session: AsyncSession, documento: DocumentoPRL, datos: DocumentoPRLUpdate
) -> DocumentoPRL:
    cambios = datos.model_dump(exclude_unset=True)
    if "tipo_id" in cambios and cambios["tipo_id"] is not None:
        tipo = await obtener_tipo(session, cambios["tipo_id"])
        if tipo is None:
            raise TipoInvalido("El tipo de documento no existe en esta organización")
    for campo, valor in cambios.items():
        setattr(documento, campo, valor)
    await session.flush()
    return documento


async def obtener_documento(session: AsyncSession, documento_id: uuid.UUID) -> DocumentoPRL | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(DocumentoPRL).where(
            DocumentoPRL.id == documento_id, DocumentoPRL.organization_id == org_id
        )
    )


async def listar_documentos(
    session: AsyncSession,
    *,
    ambito: str | None = None,
    entidad_id: uuid.UUID | None = None,
    solo_problemas: bool = False,
) -> list[DocumentoPRLOut]:
    """Documentos ya enriquecidos con el nombre del tipo, el del fichero y su
    estado de vigencia — el cliente no debería tener que recalcular la regla
    de caducidad ni pedir el catálogo aparte para pintar una lista."""
    from app.modules.documentos.models import Documento

    org_id = require_organization_id()
    filtros = [DocumentoPRL.organization_id == org_id]
    if ambito:
        filtros.append(DocumentoPRL.ambito == ambito)
    if entidad_id is not None:
        filtros.append(DocumentoPRL.entidad_id == entidad_id)

    filas = await session.execute(
        select(DocumentoPRL, TipoDocumentoPRL.nombre, Documento.nombre_archivo)
        .join(TipoDocumentoPRL, TipoDocumentoPRL.id == DocumentoPRL.tipo_id)
        .outerjoin(Documento, Documento.id == DocumentoPRL.documento_id)
        .where(*filtros)
        .order_by(DocumentoPRL.fecha_caducidad)
    )

    hoy = date.today()
    salida: list[DocumentoPRLOut] = []
    for documento, tipo_nombre, nombre_archivo in filas:
        estado = estado_de(documento.fecha_caducidad, documento.documento_id is not None, hoy)
        if solo_problemas and estado == EstadoVigencia.VIGENTE:
            continue
        item = DocumentoPRLOut.model_validate(documento)
        item.tipo_nombre = tipo_nombre
        item.nombre_archivo = nombre_archivo
        item.estado = estado
        item.dias_para_caducar = (documento.fecha_caducidad - hoy).days
        salida.append(item)
    return salida


async def resumen_vigencia(
    session: AsyncSession, *, ambito: str, entidad_id: uuid.UUID | None
) -> ResumenVigencia:
    """El semáforo, y además QUÉ falta: sin la lista de obligatorios sin
    aportar, un «todo vigente» puede significar simplemente que no se ha
    registrado nada."""
    documentos = await listar_documentos(session, ambito=ambito, entidad_id=entidad_id)
    resumen = ResumenVigencia(total=len(documentos))
    for documento in documentos:
        if documento.estado == EstadoVigencia.CADUCADO:
            resumen.caducados += 1
        elif documento.estado == EstadoVigencia.POR_CADUCAR:
            resumen.por_caducar += 1
        elif documento.estado == EstadoVigencia.PENDIENTE:
            resumen.pendientes += 1
        else:
            resumen.vigentes += 1

    tipos_presentes = {d.tipo_id for d in documentos}
    obligatorios = await listar_tipos(session, ambito=ambito)
    resumen.faltan_obligatorios = [
        t.nombre for t in obligatorios if t.obligatorio and t.id not in tipos_presentes
    ]
    return resumen


async def contar_por_entidad(
    session: AsyncSession, *, ambito: str, entidad_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Caducados y por caducar de varias entidades en UNA consulta: los
    listados de personal y recursos pintan un semáforo por fila, y hacerlo con
    una consulta por fila sería N+1 en la pantalla más usada del módulo."""
    if not entidad_ids:
        return {}
    org_id = require_organization_id()
    hoy = date.today()
    filas = await session.execute(
        select(DocumentoPRL.entidad_id, DocumentoPRL.fecha_caducidad, DocumentoPRL.documento_id).where(
            DocumentoPRL.organization_id == org_id,
            DocumentoPRL.ambito == ambito,
            DocumentoPRL.entidad_id.in_(entidad_ids),
        )
    )
    conteo: dict[uuid.UUID, tuple[int, int]] = {}
    for entidad_id, caducidad, documento_id in filas:
        caducados, por_caducar = conteo.get(entidad_id, (0, 0))
        estado = estado_de(caducidad, documento_id is not None, hoy)
        if estado == EstadoVigencia.CADUCADO:
            caducados += 1
        elif estado in (EstadoVigencia.POR_CADUCAR, EstadoVigencia.PENDIENTE):
            por_caducar += 1
        conteo[entidad_id] = (caducados, por_caducar)
    return conteo


# ── Plantillas ──────────────────────────────────────────────────────────


async def crear_plantilla(
    session: AsyncSession, datos: PlantillaDocumentoCreate
) -> PlantillaDocumento:
    from app.core.html_seguro import sanear_html

    org_id = require_organization_id()
    base = datos.codigo or _slug(datos.nombre)
    codigo = await _codigo_libre(session, PlantillaDocumento, base, org_id)
    valores = datos.model_dump(exclude={"codigo"})
    # Acaba renderizándose en una página pública para un tercero sin sesión:
    # HTML sin sanear aquí sería XSS servido a alguien de fuera.
    valores["contenido"] = sanear_html(valores.get("contenido")) or ""
    plantilla = PlantillaDocumento(
        organization_id=org_id, codigo=codigo, **valores, **datos_autoria()
    )
    session.add(plantilla)
    await session.flush()
    return plantilla


async def actualizar_plantilla(
    session: AsyncSession, plantilla: PlantillaDocumento, datos: PlantillaDocumentoUpdate
) -> PlantillaDocumento:
    from app.core.html_seguro import sanear_html

    cambios = datos.model_dump(exclude_unset=True)
    if "contenido" in cambios:
        cambios["contenido"] = sanear_html(cambios["contenido"]) or ""
    for campo, valor in cambios.items():
        setattr(plantilla, campo, valor)
    await session.flush()
    return plantilla


async def obtener_plantilla(
    session: AsyncSession, plantilla_id: uuid.UUID
) -> PlantillaDocumento | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(PlantillaDocumento).where(
            PlantillaDocumento.id == plantilla_id, PlantillaDocumento.organization_id == org_id
        )
    )


async def listar_plantillas(
    session: AsyncSession, *, ambito: str | None = None, solo_activas: bool = False
) -> list[PlantillaDocumento]:
    org_id = require_organization_id()
    filtros = [PlantillaDocumento.organization_id == org_id]
    if ambito:
        filtros.append(PlantillaDocumento.ambito == ambito)
    if solo_activas:
        filtros.append(PlantillaDocumento.activa.is_(True))
    filas = await session.scalars(
        select(PlantillaDocumento).where(*filtros).order_by(PlantillaDocumento.nombre)
    )
    return list(filas)


# ── Ficha PRL de una obra ───────────────────────────────────────────────


async def avisos_personal_de_obra(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    """Trabajadores asignados a la obra con algo caducado. Mira tanto los
    campos de la ficha (TPC, reconocimiento médico) como sus documentos PRL:
    los dos sitios acreditan cosas distintas y a la inspección le da igual en
    cuál esté el fallo."""
    from app.modules.obras.models import Asignacion, Personal

    org_id = require_organization_id()
    hoy = date.today()
    filas = await session.execute(
        select(Personal)
        .join(Asignacion, Asignacion.personal_id == Personal.id)
        .where(Asignacion.obra_id == obra_id, Personal.organization_id == org_id)
        .distinct()
    )
    personas = list(filas.scalars())
    if not personas:
        return []

    conteo = await contar_por_entidad(
        session, ambito=AmbitoPRL.PERSONAL, entidad_ids=[p.id for p in personas]
    )
    avisos = []
    for persona in personas:
        motivos: list[str] = []
        if persona.tpc_caducidad and persona.tpc_caducidad < hoy:
            motivos.append("TPC caducada")
        if persona.proximo_reconocimiento and persona.proximo_reconocimiento < hoy:
            motivos.append("Reconocimiento médico vencido")
        if persona.aptitud_medica == "no_apto":
            motivos.append("No apto médicamente")
        if not persona.formacion_prl_horas:
            motivos.append("Sin formación PRL registrada")
        caducados, por_caducar = conteo.get(persona.id, (0, 0))
        if caducados:
            motivos.append(f"{caducados} documento(s) caducado(s)")
        if por_caducar:
            motivos.append(f"{por_caducar} por caducar o sin aportar")
        if motivos:
            nombre = f"{persona.nombre} {persona.apellidos or ''}".strip()
            avisos.append({"personal_id": persona.id, "nombre": nombre, "motivos": motivos})
    return avisos
