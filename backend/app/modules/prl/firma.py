"""Circuito de firma: mandar un documento a un tercero y guardar la evidencia.

Es el segundo espacio de la aplicación sin sesión, después de la separata del
proveedor, y sigue punto por punto las mismas reglas que documenta
`compras/publico_acceso.py` (léelo: explica el porqué de cada una a fondo).
En resumen:

- `FirmaToken` está FUERA de RLS y es lo único que se toca sin contexto: solo
  sabe traducir un hash en una organización. A partir de ahí se fija el
  contexto completo y **RLS vuelve a ser el cortafuegos**.
- Las tres fuentes de identidad se fijan a la vez y todas desde el token.
- El principal sintético no lleva ningún rol.
- Un único 404 para todo: token desconocido, caducado, ya firmado o
  cancelado. Distinguirlos confirmaría que ese enlace existió.

Sobre el valor legal de lo que se guarda: esto es **firma electrónica simple
con evidencias** en el sentido del art. 3.10 del reglamento eIDAS. Se
conserva el documento exacto que se mostró, el trazo, quién dijo ser el
firmante, su IP, su navegador y tres sellos de tiempo (envío, apertura,
firma). NO es firma avanzada ni cualificada: no hay certificado que vincule
criptográficamente al firmante. Para lo que se usa aquí —acuses de recibo,
actas de coordinación de actividades empresariales, entrega de
documentación— es lo habitual en el sector, pero conviene no venderlo como
más de lo que es.
"""

import hashlib
import io
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.database import fijar_organizacion_activa, get_session
from app.core.enlaces import generar_token, hashear_token
from app.core.mensajeria import (
    Adjunto,
    Canal,
    Destinatario,
    Mensaje,
    MensajeriaError,
    TipoMensaje,
    proveedor_de,
)
from app.core.numeracion import siguiente_referencia_libre
from app.core.tenancy import (
    datos_autoria,
    require_organization_id,
    reset_organization_id,
    reset_principal,
    set_organization_id,
    set_principal,
)
from app.modules.prl.models import (
    EstadoFirma,
    EstadoFirmante,
    Firmante,
    FirmaToken,
    OrigenFirma,
    SolicitudFirma,
)
from app.modules.prl.schemas import FirmarIn, SolicitudFirmaCreate, SolicitudFirmaUpdate

logger = logging.getLogger(__name__)

#: Estados del FIRMANTE en los que su enlace todavía admite acción.
_ESTADOS_ABIERTOS = frozenset({EstadoFirmante.PENDIENTE, EstadoFirmante.VISTA})


class PlantillaInvalida(Exception):
    pass


class EstadoInvalido(Exception):
    pass


class DocumentoInvalido(Exception):
    pass


async def siguiente_codigo(session: AsyncSession) -> str:
    org_id = require_organization_id()

    async def existe(codigo: str) -> bool:
        return (
            await session.scalar(
                select(SolicitudFirma.id).where(
                    SolicitudFirma.organization_id == org_id, SolicitudFirma.codigo == codigo
                )
            )
        ) is not None

    return await siguiente_referencia_libre(
        session, organization_id=org_id, tipo_documento="solicitud_firma", existe=existe
    )


def _rellenar(plantilla: str, valores: dict[str, str]) -> str:
    """Sustitución de marcadores `{{clave}}`. A propósito NO es Jinja: la
    plantilla la escribe un usuario desde el navegador, y un motor con lógica
    y acceso a atributos sería ejecución de código arbitrario en el servidor
    (SSTI). Aquí solo se reemplaza texto por texto."""
    salida = plantilla
    for clave, valor in valores.items():
        salida = salida.replace("{{" + clave + "}}", valor or "")
    return salida


async def crear_solicitud(session: AsyncSession, datos: SolicitudFirmaCreate) -> SolicitudFirma:
    from app.core.html_seguro import sanear_html
    from app.modules.prl.service import obtener_plantilla

    org_id = require_organization_id()

    contenido = datos.contenido_html or ""
    origen = OrigenFirma.HTML

    if datos.documento_origen_id is not None:
        # Un PDF ya existente: ni se regenera ni se toca. Se comprueba que
        # exista en ESTA organización (RLS ya lo acota, pero un id de otra
        # cuenta debe dar error claro, no un 500 al descargarlo después) y que
        # de verdad sea un PDF: el firmante lo abre en el navegador y el
        # sellado final asume que se puede fusionar.
        from app.modules.documentos.models import Documento

        fila = (
            await session.execute(
                select(Documento.content_type, Documento.nombre_archivo).where(
                    Documento.id == datos.documento_origen_id,
                    Documento.organization_id == org_id,
                )
            )
        ).first()
        if fila is None:
            raise DocumentoInvalido("El documento indicado no existe en esta organización")
        if (fila.content_type or "").lower() != "application/pdf":
            raise DocumentoInvalido(
                f"Solo se puede mandar a firmar un PDF; «{fila.nombre_archivo}» es "
                f"{fila.content_type or 'de tipo desconocido'}"
            )
        origen = OrigenFirma.PDF
        contenido = ""
    elif datos.plantilla_id is not None:
        plantilla = await obtener_plantilla(session, datos.plantilla_id)
        if plantilla is None:
            raise PlantillaInvalida("La plantilla no existe en esta organización")
        contenido = plantilla.contenido
        origen = OrigenFirma.PLANTILLA

    obra_nombre = ""
    if datos.obra_id is not None:
        from app.modules.obras.models import Obra

        obra_nombre = await session.scalar(
            select(Obra.nombre).where(Obra.id == datos.obra_id, Obra.organization_id == org_id)
        ) or ""

    emisor = await _nombre_emisor(session, org_id)
    contenido = _rellenar(
        contenido,
        {
            # Con varios firmantes el marcador no puede señalar a uno solo:
            # se ponen todos, separados por comas.
            "destinatario": ", ".join(f.nombre for f in datos.firmantes),
            "obra": obra_nombre,
            "emisor": emisor or "",
            "fecha": datetime.now(UTC).strftime("%d/%m/%Y"),
        },
    )

    solicitud = SolicitudFirma(
        organization_id=org_id,
        codigo=await siguiente_codigo(session),
        titulo=datos.titulo,
        origen=origen,
        # Foto del documento tal cual se manda: si luego cambia la plantilla,
        # lo que se firmó tiene que seguir siendo lo que el firmante vio.
        contenido_html=sanear_html(contenido) or "",
        documento_origen_id=datos.documento_origen_id,
        plantilla_id=datos.plantilla_id,
        obra_id=datos.obra_id,
        tercero_id=datos.tercero_id,
        estado=EstadoFirma.BORRADOR,
        expira_en=datetime.now(UTC) + timedelta(days=datos.dias_validez),
        canal_enlace=datos.canal_enlace,
        canal_codigo=datos.canal_codigo,
        **datos_autoria(),
    )
    session.add(solicitud)
    await session.flush()

    for orden, entrada in enumerate(datos.firmantes):
        session.add(
            Firmante(
                organization_id=org_id,
                solicitud_id=solicitud.id,
                orden=orden,
                nombre=entrada.nombre,
                email=entrada.email,
                telefono=entrada.telefono,
                contacto_id=entrada.contacto_id,
                estado=EstadoFirmante.PENDIENTE,
            )
        )
    await session.flush()
    return solicitud


async def listar_firmantes(session: AsyncSession, solicitud_id: uuid.UUID) -> list[Firmante]:
    filas = await session.scalars(
        select(Firmante).where(Firmante.solicitud_id == solicitud_id).order_by(Firmante.orden)
    )
    return list(filas)


def estado_agregado(firmantes: list[Firmante]) -> EstadoFirma:
    """El estado del DOCUMENTO se deduce de sus firmantes, no se lleva a mano:
    dos fuentes de verdad para lo mismo acaban discrepando en cuanto una
    ruta de código se olvide de actualizar la otra.

    Un rechazo manda sobre todo lo demás: si alguien se niega a firmar, el
    documento no está «parcialmente firmado», está rechazado."""
    if not firmantes:
        return EstadoFirma.BORRADOR
    if any(f.estado == EstadoFirmante.RECHAZADA for f in firmantes):
        return EstadoFirma.RECHAZADA
    firmados = sum(1 for f in firmantes if f.estado == EstadoFirmante.FIRMADA)
    if firmados == len(firmantes):
        return EstadoFirma.FIRMADA
    if firmados > 0:
        return EstadoFirma.PARCIAL
    if any(f.estado == EstadoFirmante.VISTA for f in firmantes):
        return EstadoFirma.VISTA
    return EstadoFirma.ENVIADA


async def actualizar_solicitud(
    session: AsyncSession, solicitud: SolicitudFirma, datos: SolicitudFirmaUpdate
) -> SolicitudFirma:
    from app.core.html_seguro import sanear_html

    if solicitud.estado != EstadoFirma.BORRADOR:
        raise EstadoInvalido("Solo se puede editar una solicitud en borrador")
    cambios = datos.model_dump(exclude_unset=True)
    if "contenido_html" in cambios:
        cambios["contenido_html"] = sanear_html(cambios["contenido_html"]) or ""
    for campo, valor in cambios.items():
        setattr(solicitud, campo, valor)
    await session.flush()
    return solicitud


async def _nombre_emisor(session: AsyncSession, organization_id: uuid.UUID) -> str:
    return (
        await session.scalar(
            text("SELECT name FROM core.organization WHERE id = :org_id"),
            {"org_id": str(organization_id)},
        )
        or ""
    )


#: Estados en los que el documento ya no admite tocar la lista de firmantes.
#: Con la firma cerrada existe un PDF sellado con unas firmas concretas;
#: añadir a alguien después dejaría ese PDF mintiendo sobre quién firmaba.
_ESTADOS_CERRADOS = frozenset(
    {EstadoFirma.FIRMADA, EstadoFirma.RECHAZADA, EstadoFirma.CANCELADA}
)


async def anadir_firmante(
    session: AsyncSession, solicitud: SolicitudFirma, entrada
) -> Firmante:
    """Suma un firmante a una solicitud ya creada — el caso de «se me olvidó
    uno», que antes obligaba a rehacer la solicitud entera.

    El documento vuelve a quedar incompleto, y su estado se recalcula solo a
    partir de los firmantes (ver `estado_agregado`)."""
    if solicitud.estado in _ESTADOS_CERRADOS:
        raise EstadoInvalido(
            "Este documento ya está cerrado; crea una solicitud nueva para más firmas"
        )

    firmantes = await listar_firmantes(session, solicitud.id)
    if any(f.email.lower() == entrada.email.lower().strip() for f in firmantes):
        raise EstadoInvalido(f"{entrada.email} ya está en la lista de firmantes")

    firmante = Firmante(
        organization_id=solicitud.organization_id,
        solicitud_id=solicitud.id,
        orden=max((f.orden for f in firmantes), default=-1) + 1,
        nombre=entrada.nombre,
        email=entrada.email,
        telefono=entrada.telefono,
        contacto_id=entrada.contacto_id,
        estado=EstadoFirmante.PENDIENTE,
    )
    session.add(firmante)
    await session.flush()

    solicitud.estado = estado_agregado(await listar_firmantes(session, solicitud.id))
    await session.flush()
    return firmante


async def quitar_firmante(
    session: AsyncSession, solicitud: SolicitudFirma, firmante_id: uuid.UUID
) -> None:
    """Saca a alguien de la lista. Solo si todavía no ha respondido: una firma
    o un rechazo son evidencia y no se borran para dejar el documento más
    cómodo."""
    if solicitud.estado in _ESTADOS_CERRADOS:
        raise EstadoInvalido("Este documento ya está cerrado")

    firmantes = await listar_firmantes(session, solicitud.id)
    objetivo = next((f for f in firmantes if f.id == firmante_id), None)
    if objetivo is None:
        raise EstadoInvalido("Ese firmante no es de este documento")
    if objetivo.estado not in _ESTADOS_ABIERTOS:
        raise EstadoInvalido(
            f"{objetivo.nombre} ya ha respondido; su firma es parte de la evidencia"
        )
    if len(firmantes) == 1:
        raise EstadoInvalido(
            "Un documento sin firmantes no tiene sentido; cancélalo en vez de vaciarlo"
        )

    # Su token cae por CASCADE: el enlace que tuviera deja de valer, que es
    # justo lo que se quiere al sacar a alguien de la lista.
    await session.delete(objetivo)
    await session.flush()

    restantes = await listar_firmantes(session, solicitud.id)
    solicitud.estado = estado_agregado(restantes)
    await session.flush()

    # Quitar al último pendiente puede COMPLETAR el documento: si los demás ya
    # habían firmado, con este fuera ya no falta nadie. Hay que sellarlo aquí
    # o quedaría marcado como firmado pero sin el PDF con las firmas, porque
    # nadie más va a pasar por `firmar()`.
    if solicitud.estado == EstadoFirma.FIRMADA and solicitud.documento_id is None:
        await _generar_pdf_final(
            session,
            solicitud,
            restantes,
            await _nombre_emisor(session, solicitud.organization_id),
        )


async def obtener_solicitud(
    session: AsyncSession, solicitud_id: uuid.UUID
) -> SolicitudFirma | None:
    org_id = require_organization_id()
    return await session.scalar(
        select(SolicitudFirma).where(
            SolicitudFirma.id == solicitud_id, SolicitudFirma.organization_id == org_id
        )
    )


async def listar_solicitudes(
    session: AsyncSession,
    *,
    obra_id: uuid.UUID | None = None,
    estado: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SolicitudFirma], int]:
    org_id = require_organization_id()
    filtros = [SolicitudFirma.organization_id == org_id]
    if obra_id:
        filtros.append(SolicitudFirma.obra_id == obra_id)
    if estado:
        filtros.append(SolicitudFirma.estado == estado)
    total = (
        await session.scalar(select(func.count()).select_from(SolicitudFirma).where(*filtros)) or 0
    )
    filas = await session.scalars(
        select(SolicitudFirma)
        .where(*filtros)
        .order_by(SolicitudFirma.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(filas), total


async def preparar_envio(
    session: AsyncSession, solicitud: SolicitudFirma, firmante: Firmante
) -> str:
    """Genera el enlace de UN firmante y lo marca como enviado. Devuelve el
    token en claro, que es lo ÚNICO que no se guarda: a partir de aquí solo
    existe en su correo."""
    if firmante.estado not in _ESTADOS_ABIERTOS:
        raise EstadoInvalido(
            f"{firmante.nombre} ya ha {'firmado' if firmante.estado == EstadoFirmante.FIRMADA else 'respondido'}"
        )

    token, token_hash = generar_token()
    # Reenviar invalida el enlace anterior de ESE firmante: si alguien
    # reenvía es justamente porque el primero se perdió o llegó a quien no
    # debía. Los enlaces de los demás no se tocan.
    for antiguo in await session.scalars(
        select(FirmaToken).where(FirmaToken.firmante_id == firmante.id)
    ):
        await session.delete(antiguo)

    session.add(
        FirmaToken(
            organization_id=solicitud.organization_id,
            token_hash=token_hash,
            firmante_id=firmante.id,
        )
    )
    firmante.enviada_en = datetime.now(UTC)
    if solicitud.estado == EstadoFirma.BORRADOR:
        solicitud.estado = EstadoFirma.ENVIADA
    if solicitud.expira_en is None or solicitud.expira_en <= datetime.now(UTC):
        solicitud.expira_en = datetime.now(UTC) + timedelta(days=30)
    await session.flush()
    return token


# ── Espacio público ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class ContextoFirma:
    solicitud: SolicitudFirma
    #: QUIÉN está entrando. El token identifica a una persona concreta dentro
    #: del documento, y todo lo que se escriba queda acotado a ella.
    firmante: Firmante
    organization_id: uuid.UUID
    emisor: str


def _no_encontrado() -> HTTPException:
    """Siempre el mismo error, diga lo que diga el motivo real."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Este enlace no es válido, ya se ha usado o ha caducado.",
    )


async def acceso_firma(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Dependencia de todo endpoint bajo `/api/publico/firma/{token}`."""
    if not token or len(token) > 200:
        raise _no_encontrado()
    acceso = await session.scalar(
        select(FirmaToken).where(FirmaToken.token_hash == hashear_token(token))
    )
    if acceso is None:
        raise _no_encontrado()

    # Nadie debería haber fijado identidad antes: el middleware se salta este
    # espacio. Si hay algo, es que la ruta dejó de ser pública sin querer.
    if getattr(request.state, "principal", None) is not None:
        raise RuntimeError(
            "La ruta pública de firma recibió un principal ya autenticado; "
            "revisa PUBLIC_PREFIXES en app/core/middleware.py"
        )

    org_id = acceso.organization_id
    await fijar_organizacion_activa(session, org_id)
    token_org = set_organization_id(org_id)

    fila = (
        await session.execute(
            text("SELECT slug, name FROM core.organization WHERE id = :org_id"),
            {"org_id": str(org_id)},
        )
    ).first()
    principal = Principal(
        subject=f"firmante:{acceso.firmante_id}",
        organization_id=org_id,
        organization_slug=fila.slug if fila else None,
        username="Firmante (enlace externo)",
        roles=frozenset(),  # sin roles: no supera ninguna guarda de la aplicación
    )
    token_principal = set_principal(principal)
    request.state.principal = principal

    try:
        firmante = await session.scalar(select(Firmante).where(Firmante.id == acceso.firmante_id))
        if firmante is None:
            raise _no_encontrado()
        solicitud = await session.scalar(
            select(SolicitudFirma).where(SolicitudFirma.id == firmante.solicitud_id)
        )
        if solicitud is None:
            raise _no_encontrado()
        if solicitud.expira_en is not None and solicitud.expira_en <= datetime.now(UTC):
            raise _no_encontrado()
        # Un firmante que ya firmó sigue pudiendo ver lo que firmó; el
        # documento cancelado o rechazado, no.
        if solicitud.estado in (EstadoFirma.CANCELADA, EstadoFirma.RECHAZADA):
            raise _no_encontrado()
        if solicitud.estado == EstadoFirma.BORRADOR:
            raise _no_encontrado()

        yield ContextoFirma(
            solicitud=solicitud,
            firmante=firmante,
            organization_id=org_id,
            emisor=fila.name if fila else "",
        )
        # Con el principal todavía en contexto, para que la auditoría tenga
        # autor. El commit lo hace `get_session`, nunca el router.
        await session.flush()
    finally:
        request.state.principal = None
        reset_principal(token_principal)
        reset_organization_id(token_org)


# ── Código de un solo uso (segundo factor) ──────────────────────────────

#: Seis dígitos. Con 5 intentos y 10 minutos de vida, adivinarlo es 5/1.000.000
#: por código — el límite de intentos es lo que hace segura una longitud
#: cómoda de teclear, no la longitud en sí.
_DIGITOS_OTP = 6
_MINUTOS_OTP = 10
MAX_INTENTOS_OTP = 5


def _hash_otp(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()


async def generar_otp(session: AsyncSession, firmante: Firmante) -> str:
    """Nuevo código y devuelve el CLARO, que solo viaja en el correo. Pedir
    otro invalida el anterior y reinicia los intentos: si alguien pide un
    código nuevo es justamente porque el anterior no le sirve."""
    codigo = f"{secrets.randbelow(10**_DIGITOS_OTP):0{_DIGITOS_OTP}d}"
    firmante.otp_hash = _hash_otp(codigo)
    firmante.otp_expira_en = datetime.now(UTC) + timedelta(minutes=_MINUTOS_OTP)
    firmante.otp_intentos = 0
    await session.flush()
    return codigo


def verificar_otp(firmante: Firmante, codigo: str) -> None:
    """Lanza `EstadoInvalido` con un motivo entendible si no cuadra. Cuenta
    los intentos en la propia fila: sin contador, un código de seis dígitos se
    prueba entero por fuerza bruta en minutos."""
    if not firmante.otp_hash or not firmante.otp_expira_en:
        raise EstadoInvalido("Pide un código de verificación antes de firmar")
    if firmante.otp_expira_en <= datetime.now(UTC):
        raise EstadoInvalido("El código ha caducado; pide uno nuevo")
    if firmante.otp_intentos >= MAX_INTENTOS_OTP:
        raise EstadoInvalido("Demasiados intentos fallidos; pide un código nuevo")
    # `compare_digest` y no `==`: comparar hashes con el operador normal filtra
    # información por el tiempo que tarda en fallar.
    if not secrets.compare_digest(firmante.otp_hash, _hash_otp(codigo.strip())):
        firmante.otp_intentos += 1
        restantes = MAX_INTENTOS_OTP - firmante.otp_intentos
        raise EstadoInvalido(
            f"Código incorrecto. Te quedan {restantes} intento(s)."
            if restantes > 0
            else "Código incorrecto. Pide un código nuevo."
        )


async def marcar_vista(session: AsyncSession, contexto: "ContextoFirma") -> None:
    """Primera apertura del enlace por ESTE firmante. Solo la primera:
    `vista_en` es parte de la evidencia («se le enseñó el documento el día
    X»), no un contador de visitas, así que no se pisa en cada recarga."""
    firmante = contexto.firmante
    if firmante.estado != EstadoFirmante.PENDIENTE:
        return
    firmante.estado = EstadoFirmante.VISTA
    firmante.vista_en = datetime.now(UTC)
    # El documento solo baja a "vista" si nadie ha firmado todavía: no puede
    # retroceder desde "parcial" porque uno más abra el enlace.
    if contexto.solicitud.estado == EstadoFirma.ENVIADA:
        contexto.solicitud.estado = EstadoFirma.VISTA
    await session.flush()


def _pdf_firmado(
    solicitud: SolicitudFirma,
    emisor: str,
    firmantes: list[Firmante],
    *,
    solo_evidencia: bool = False,
) -> bytes:
    """Documento + firma + evidencias, en un PDF. WeasyPrint ya está en el
    stack (lo usa `facturacion/informes.py`).

    Con `solo_evidencia`, omite el cuerpo del documento y genera únicamente la
    hoja de firma: es lo que se anexa al final de un PDF que ya existía, para
    no reconstruirlo (ver `_pdf_firmado_desde_original`)."""
    from weasyprint import HTML

    def _cuando(momento) -> str:
        return momento.strftime("%d/%m/%Y %H:%M UTC") if momento else "—"

    # Una ficha por firmante: cada firma es un acto independiente con sus
    # propias evidencias, y agruparlas en una sola tabla haría imposible saber
    # qué IP corresponde a quién.
    fichas = ""
    for firmante in firmantes:
        if firmante.estado != EstadoFirmante.FIRMADA:
            estado = "RECHAZÓ LA FIRMA" if firmante.estado == EstadoFirmante.RECHAZADA else "PENDIENTE"
            motivo = f"<br>Motivo: {firmante.motivo_rechazo}" if firmante.motivo_rechazo else ""
            fichas += (
                f'<div class="firma"><strong>{firmante.nombre}</strong> — {estado}{motivo}</div>'
            )
            continue
        fichas += f'''
          <div class="firma">
            <strong>Firmado electrónicamente por:</strong><br>
            {firmante.firmante_nombre or firmante.nombre}{f" · {firmante.firmante_dni}" if firmante.firmante_dni else ""}
            <img src="{firmante.firma_imagen or ""}" alt="Firma">
            <table class="evidencias">
              <tr><td>Documento enviado a</td><td>{firmante.email}</td></tr>
              <tr><td>Fecha de envío</td><td>{_cuando(firmante.enviada_en)}</td></tr>
              <tr><td>Primera apertura</td><td>{_cuando(firmante.vista_en)}</td></tr>
              <tr><td>Fecha de firma</td><td>{_cuando(firmante.firmada_en)}</td></tr>
              <tr><td>Código verificado</td><td>{_cuando(firmante.otp_verificado_en)}</td></tr>
              <tr><td>Dirección IP</td><td>{firmante.ip_firma or "—"}</td></tr>
              <tr><td>Navegador</td><td>{(firmante.user_agent_firma or "—")[:110]}</td></tr>
            </table>
          </div>'''
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: sans-serif; font-size: 11pt; color: #111; }}
  .cabecera {{ border-bottom: 2px solid #333; padding-bottom: 8px; margin-bottom: 20px; }}
  .cabecera h1 {{ font-size: 15pt; margin: 0 0 4px; }}
  .meta {{ font-size: 9pt; color: #555; }}
  .contenido {{ margin-bottom: 30px; line-height: 1.5; }}
  .firma {{ border: 1px solid #ccc; padding: 14px; page-break-inside: avoid; }}
  .firma img {{ max-height: 90px; display: block; margin: 8px 0; }}
  .evidencias {{ margin-top: 14px; font-size: 8.5pt; color: #555; }}
  .evidencias td {{ padding: 2px 10px 2px 0; vertical-align: top; }}
  .aviso {{ margin-top: 16px; font-size: 8pt; color: #777; font-style: italic; }}
</style></head><body>
  <div class="cabecera">
    <h1>{solicitud.titulo}</h1>
    <div class="meta">{emisor} · Documento {solicitud.codigo}</div>
  </div>
  <div class="contenido">{"" if solo_evidencia else solicitud.contenido_html}</div>
  {fichas}
  <div class="aviso">
    Firma electrónica simple con evidencias (art. 3.10 del Reglamento UE 910/2014),
    con verificación en dos pasos por correo. No constituye firma electrónica
    avanzada ni cualificada.<br>
    Referencia {solicitud.codigo} · Huella SHA-256 del documento firmado:
    {solicitud.hash_documento or "(se calcula al cerrar)"}
  </div>
</body></html>"""
    return HTML(string=html).write_pdf()


async def _pdf_original(session: AsyncSession, documento_id: uuid.UUID) -> bytes:
    from app.core import storage
    from app.modules.documentos.models import Documento

    clave = await session.scalar(select(Documento.object_key).where(Documento.id == documento_id))
    if clave is None:
        raise DocumentoInvalido("El documento original ya no está disponible")
    return await storage.descargar_objeto(clave)


def _capa(ancho: float, alto: float, html_cuerpo: str) -> "PdfReader":
    """Una página transparente del tamaño dado con `html_cuerpo` encima, lista
    para superponer sobre una página del PDF original."""
    from pypdf import PdfReader
    from weasyprint import HTML

    pdf = HTML(
        string=f"""<!doctype html><html><head><meta charset="utf-8"><style>
          @page {{ size: {ancho}pt {alto}pt; margin: 0; }}
          body {{ margin: 0; font-family: sans-serif; }}
        </style></head><body>{html_cuerpo}</body></html>"""
    ).write_pdf()
    return PdfReader(io.BytesIO(pdf))


def _html_sello(solicitud: SolicitudFirma, firmantes: list[Firmante]) -> str:
    """Sello en la esquina inferior izquierda, en todas las páginas: quien abre
    el PDF tiene que ver que está firmado sin llegar a la última hoja.

    Semitransparente (`opacity`) para no tapar el contenido del documento
    original — un sello opaco encima de una tabla o una cota deja el PDF
    inservible justo donde cae."""
    lineas = ""
    for firmante in firmantes:
        if firmante.estado != EstadoFirmante.FIRMADA:
            continue
        cuando = firmante.firmada_en.strftime("%d/%m/%Y %H:%M") if firmante.firmada_en else ""
        dni = f" · {firmante.firmante_dni}" if firmante.firmante_dni else ""
        lineas += f"<div>{firmante.firmante_nombre or firmante.nombre}{dni} — {cuando}</div>"
    return f"""
      <div style="position:absolute; left:14pt; bottom:14pt; max-width:250pt;
                  border-left:3pt solid #16803d; padding:4pt 7pt;
                  background:#f0fdf4; font-size:6.5pt; opacity:0.62;
                  color:#14532d; line-height:1.35;">
        <div style="font-weight:700; font-size:7pt;">FIRMADO ELECTRÓNICAMENTE</div>
        {lineas}
        <div style="color:#3f6212;">Ref. {solicitud.codigo} · evidencias en la última página</div>
      </div>"""


def _html_firma_posicionada(firmante: Firmante, posicion: dict) -> str:
    """La imagen de la firma donde el emisor la colocó en el visor. Las
    coordenadas llegan en fracciones (0-1) del tamaño de página, así que aquí
    se traducen a porcentajes — sin depender de a qué escala se pintó."""
    return f"""
      <img src="{firmante.firma_imagen or ''}"
           style="position:absolute;
                  left:{float(posicion.get('x', 0)) * 100:.2f}%;
                  top:{float(posicion.get('y', 0)) * 100:.2f}%;
                  width:{float(posicion.get('ancho', 0.25)) * 100:.2f}%;
                  height:{float(posicion.get('alto', 0.08)) * 100:.2f}%;
                  object-fit:contain;">"""


def _sellar(
    original: bytes, evidencia: bytes, solicitud: SolicitudFirma, firmantes: list[Firmante]
) -> bytes:
    """El PDF original con el sello encima, más la hoja de evidencias al final.

    El CONTENIDO original no se reescribe: el sello y la firma se superponen
    como una capa aparte, así que el texto y las imágenes del documento que se
    firmó siguen siendo exactamente los mismos objetos del PDF de partida.

    Si el emisor colocó firmas en el visor (`posiciones_firma`), se pintan
    además en la página y el sitio que indicó."""
    from pypdf import PdfReader, PdfWriter

    lector = PdfReader(io.BytesIO(original))
    escritor = PdfWriter()

    for numero, pagina in enumerate(lector.pages):
        ancho = float(pagina.mediabox.width)
        alto = float(pagina.mediabox.height)
        cuerpo = _html_sello(solicitud, firmantes)
        for firmante in firmantes:
            if firmante.estado != EstadoFirmante.FIRMADA:
                continue
            for posicion in firmante.posiciones_firma or []:
                if int(posicion.get("pagina", 0)) == numero:
                    cuerpo += _html_firma_posicionada(firmante, posicion)
        try:
            pagina.merge_page(_capa(ancho, alto, cuerpo).pages[0])
        except Exception:  # noqa: BLE001
            # Una página que no admita la superposición (rotada de forma rara,
            # con recursos corruptos) no puede impedir que se firme: se queda
            # sin sello, pero la hoja de evidencias del final sigue estando y
            # es la que tiene valor probatorio.
            logger.warning("No se pudo sellar la página %s de %s", numero + 1, solicitud.codigo)
        escritor.add_page(pagina)

    for pagina in PdfReader(io.BytesIO(evidencia)).pages:
        escritor.add_page(pagina)
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


async def firmar(
    session: AsyncSession,
    contexto: ContextoFirma,
    datos: FirmarIn,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[SolicitudFirma, bool]:
    """Registra la firma de UN firmante. Devuelve `(solicitud, se_cerró)`.

    El PDF sellado solo se genera cuando han firmado TODOS: con firmas
    parciales habría que regenerarlo en cada una, y cada versión intermedia
    sería un documento "firmado" incompleto circulando por ahí."""
    solicitud = contexto.solicitud
    firmante = contexto.firmante
    if firmante.estado not in _ESTADOS_ABIERTOS:
        raise EstadoInvalido("Ya has respondido a este documento")
    # Segundo factor ANTES de nada: si el código no cuadra, no se toca nada
    # (salvo el contador de intentos, que sube dentro).
    verificar_otp(firmante, datos.codigo)
    # Solo se acepta una imagen PNG en data: URI. Sin esta comprobación, el
    # campo entraría tal cual en el `src` del PDF y en la página de la ficha:
    # un `javascript:` o un SVG con script serían XSS almacenado.
    if not datos.firma_imagen.startswith("data:image/png;base64,"):
        raise EstadoInvalido("La firma debe ser una imagen PNG")
    if len(datos.firma_imagen) > 2_000_000:
        raise EstadoInvalido("La firma es demasiado grande")

    firmante.firmante_nombre = datos.firmante_nombre
    firmante.firmante_dni = datos.firmante_dni
    firmante.firma_imagen = datos.firma_imagen
    firmante.ip_firma = (ip or "")[:45] or None
    firmante.user_agent_firma = (user_agent or "")[:400] or None
    firmante.firmada_en = datetime.now(UTC)
    firmante.otp_verificado_en = datetime.now(UTC)
    # El código no se reutiliza: gastarlo aquí impide que un reenvío del mismo
    # formulario vuelva a pasar la verificación.
    firmante.otp_hash = None
    firmante.estado = EstadoFirmante.FIRMADA
    await session.flush()

    firmantes = await listar_firmantes(session, solicitud.id)
    solicitud.estado = estado_agregado(firmantes)
    await session.flush()

    if solicitud.estado != EstadoFirma.FIRMADA:
        return solicitud, False

    await _generar_pdf_final(session, solicitud, firmantes, contexto.emisor)
    return solicitud, True


async def _generar_pdf_final(
    session: AsyncSession,
    solicitud: SolicitudFirma,
    firmantes: list[Firmante],
    emisor: str,
) -> None:
    from app.modules.documentos.models import EntidadDocumento
    from app.modules.documentos.service import subir_documento

    if solicitud.origen == OrigenFirma.PDF and solicitud.documento_origen_id:
        # El hash es del documento TAL COMO SE LE MOSTRÓ a los firmantes, no
        # del sellado: es lo que permite demostrar qué se aceptó exactamente.
        original = await _pdf_original(session, solicitud.documento_origen_id)
        solicitud.hash_documento = hashlib.sha256(original).hexdigest()
        contenido_pdf = _sellar(
            original,
            _pdf_firmado(solicitud, emisor, firmantes, solo_evidencia=True),
            solicitud,
            firmantes,
        )
    else:
        solicitud.hash_documento = hashlib.sha256(
            (solicitud.contenido_html or "").encode()
        ).hexdigest()
        contenido_pdf = _pdf_firmado(solicitud, emisor, firmantes)

    documento = await subir_documento(
        session,
        entidad=EntidadDocumento.SOLICITUD_FIRMA,
        entidad_id=solicitud.id,
        nombre_archivo=f"{solicitud.codigo}-firmado.pdf",
        content_type="application/pdf",
        contenido=contenido_pdf,
    )
    solicitud.documento_id = documento.id
    await session.flush()

    # Con el PDF ya en la mano: quien tenga WhatsApp recibe su copia sin
    # tener que entrar a buscarla.
    await enviar_documento_firmado(session, solicitud, firmantes, contenido_pdf)


async def rechazar(
    session: AsyncSession, contexto: ContextoFirma, motivo: str
) -> SolicitudFirma:
    """Un rechazo tumba el documento entero, aunque otros ya hubieran firmado:
    si una de las partes se niega, el acuerdo no existe. Las firmas ya hechas
    NO se borran — son evidencia de que esas personas sí aceptaron."""
    firmante = contexto.firmante
    if firmante.estado not in _ESTADOS_ABIERTOS:
        raise EstadoInvalido("Ya has respondido a este documento")
    firmante.estado = EstadoFirmante.RECHAZADA
    firmante.motivo_rechazo = motivo
    await session.flush()
    contexto.solicitud.estado = estado_agregado(
        await listar_firmantes(session, contexto.solicitud.id)
    )
    await session.flush()
    return contexto.solicitud




# ── Por dónde se manda cada cosa ────────────────────────────────────────
#
# Quien crea la solicitud elige (`canal_enlace` / `canal_codigo`). En `AUTO`
# —lo de fábrica— decide el dominio, y su criterio es que el enlace y su
# código de verificación NO viajen por el mismo canal: si los dos llegan al
# mismo buzón, quien tenga acceso a ese canal tiene las dos mitades y el
# segundo factor deja de ser «algo que tienes».
#
# Una elección explícita se respeta tal cual, incluso si es peor: si alguien
# pide los dos canales para todo, se hace, porque puede tener sus motivos y
# no es el código quien decide por él. Lo que NO se hace es cambiar de canal
# a escondidas — pedir WhatsApp y que salga un correo sin avisar.
#
# Nada de esto sabe si detrás de WhatsApp hay un puente de WhatsApp Web o la
# API oficial: pide un canal al puerto de mensajería. Ver `app/core/mensajeria/`.


@dataclass(frozen=True)
class _Reparto:
    """Por dónde intentarlo, y por dónde si eso falla."""

    #: Lo que se intenta primero, en orden.
    canales: list[Canal]
    #: Solo se usa si NINGUNO de los anteriores sale. Vacío cuando la
    #: elección es explícita: ahí un respaldo sería desobedecer.
    respaldo: list[Canal]


def _destinatario(firmante: Firmante) -> Destinatario:
    return Destinatario(
        nombre=firmante.nombre, email=firmante.email, telefono=firmante.telefono
    )


async def _proveedor(
    session: AsyncSession, solicitud: SolicitudFirma, canal: Canal, firmante: Firmante
):
    """El proveedor de ese canal si además puede alcanzar a ESTE firmante.

    Las dos condiciones van juntas a propósito: que WhatsApp esté configurado
    no sirve de nada si esta persona no tiene teléfono."""
    proveedor = await proveedor_de(session, solicitud.organization_id, canal)
    if proveedor is None or proveedor.direccion_de(_destinatario(firmante)) is None:
        return None
    return proveedor


async def canales_posibles(
    session: AsyncSession, solicitud: SolicitudFirma, firmante: Firmante
) -> list[Canal]:
    """Por dónde se puede alcanzar HOY a esta persona."""
    posibles = []
    for canal in Canal:
        if await _proveedor(session, solicitud, canal, firmante):
            posibles.append(canal)
    return posibles


async def reparto_para_enlace(
    session: AsyncSession, solicitud: SolicitudFirma, firmante: Firmante
) -> _Reparto:
    posibles = await canales_posibles(session, solicitud, firmante)
    pedidos = solicitud.canal_enlace.canales()
    if pedidos:
        return _Reparto([c for c in pedidos if c in posibles], [])
    # AUTO: WhatsApp si se puede — llega al momento y no cae en spam, que es
    # el fallo más común del correo.
    if Canal.WHATSAPP in posibles:
        return _Reparto([Canal.WHATSAPP], [c for c in posibles if c != Canal.WHATSAPP])
    return _Reparto(posibles[:1], [])


async def reparto_para_codigo(
    session: AsyncSession, solicitud: SolicitudFirma, firmante: Firmante
) -> _Reparto:
    posibles = await canales_posibles(session, solicitud, firmante)
    pedidos = solicitud.canal_codigo.canales()
    if pedidos:
        return _Reparto([c for c in pedidos if c in posibles], [])

    # AUTO: por donde NO haya ido el enlace, para que de verdad sean dos.
    usados = {Canal(c) for c in (firmante.canales_envio or [])}
    libres = [c for c in posibles if c not in usados]
    if libres:
        return _Reparto(libres[:1], [])
    # No queda ninguno libre: o esta persona solo tiene correo, o el enlace
    # salió por todos. Se manda por donde se pueda — es peor y conviene
    # saberlo, pero negarse la dejaría sin poder firmar.
    return _Reparto(posibles[:1], [])


async def _mandar(
    session: AsyncSession,
    solicitud: SolicitudFirma,
    firmante: Firmante,
    reparto: _Reparto,
    mensaje: Mensaje,
) -> tuple[list[Canal], str]:
    """Manda por todos los canales del reparto. Devuelve por cuáles salió de
    verdad y a dónde (tapado). Lanza solo si no salió por ninguno."""
    destinatario = _destinatario(firmante)
    ultimo_fallo: MensajeriaError | None = None

    async def intentar(canales: list[Canal]) -> tuple[list[Canal], list[str]]:
        nonlocal ultimo_fallo
        salieron, destinos = [], []
        for canal in canales:
            proveedor = await _proveedor(session, solicitud, canal, firmante)
            if proveedor is None:
                continue
            try:
                await proveedor.enviar(destinatario, mensaje)
            except MensajeriaError as exc:
                logger.warning(
                    "%s: no se pudo mandar por %s a %s: %s",
                    solicitud.codigo, canal.value, firmante.email, exc,
                )
                ultimo_fallo = exc
                continue
            salieron.append(canal)
            destinos.append(proveedor.ofuscar(destinatario))
        return salieron, destinos

    salieron, destinos = await intentar(reparto.canales)
    if not salieron and reparto.respaldo:
        salieron, destinos = await intentar(reparto.respaldo)
        if salieron:
            logger.warning(
                "%s: se usó el respaldo (%s) para %s",
                solicitud.codigo, ", ".join(c.value for c in salieron), firmante.email,
            )

    if not salieron:
        raise ultimo_fallo or MensajeriaError(
            f"No se puede llegar a {firmante.nombre} por el canal elegido"
        )
    return salieron, " y ".join(destinos)


async def enviar_enlace(
    session: AsyncSession, solicitud: SolicitudFirma, firmante: Firmante, enlace: str
) -> tuple[list[Canal], str]:
    """Manda el enlace y deja anotado por qué canales salió, que es lo que
    después decide por dónde va el código."""
    mensaje = Mensaje(
        asunto=f"Documento para firmar: {solicitud.titulo}",
        texto=(
            f"Hola {firmante.nombre}:\n\n"
            f"Tienes un documento pendiente de firma: {solicitud.titulo}\n\n"
            f"Puedes firmarlo aquí:\n{enlace}\n\n"
            f"Este enlace es personal, no lo reenvíes. "
            f"Si no esperabas este mensaje, ignóralo."
        ),
        html=(
            f"<p>Hola {firmante.nombre},</p>"
            f"<p>Tienes un documento pendiente de firma: "
            f"<strong>{solicitud.titulo}</strong>.</p>"
            # `target="_blank"`: Gmail y otros webmails abren el enlace DENTRO
            # de su propia pestaña, y ahí el visor de PDF y el lienzo de firma
            # se comportan mal.
            f'<p><a href="{enlace}" target="_blank" rel="noopener">'
            f"Abrir y firmar el documento</a></p>"
            f'<p style="font-size:12px;color:#666">Si el enlace no se abre bien, '
            f"copia esta dirección en tu navegador:<br>{enlace}</p>"
            f'<p style="font-size:12px;color:#666">Este enlace es personal. '
            f"Si no esperabas este correo, ignóralo.</p>"
        ),
        variables=(firmante.nombre, solicitud.titulo, enlace),
    )
    reparto = await reparto_para_enlace(session, solicitud, firmante)
    canales, destino = await _mandar(session, solicitud, firmante, reparto, mensaje)
    firmante.canales_envio = [c.value for c in canales]
    await session.flush()
    return canales, destino


async def enviar_codigo(
    session: AsyncSession, solicitud: SolicitudFirma, firmante: Firmante, codigo: str
) -> tuple[list[Canal], str]:
    """Manda el código de verificación. Devuelve por dónde salió y la
    dirección tapada, para poder decir «te lo hemos mandado a…»."""
    mensaje = Mensaje(
        asunto=f"Tu código para firmar: {codigo}",
        texto=(
            f"Tu código para firmar {solicitud.titulo} es: {codigo}\n\n"
            f"Caduca en {_MINUTOS_OTP} minutos. No se lo des a nadie. "
            f"Si no has sido tú, ignora este mensaje."
        ),
        html=(
            f"<p>Tu código de verificación para firmar "
            f"<strong>{solicitud.titulo}</strong> es:</p>"
            f'<p style="font-size:26px;letter-spacing:5px;font-weight:bold">{codigo}</p>'
            f"<p>Caduca en {_MINUTOS_OTP} minutos. "
            f"Si no has sido tú, ignora este correo.</p>"
        ),
        tipo=TipoMensaje.CODIGO_VERIFICACION,
        variables=(codigo, str(_MINUTOS_OTP)),
    )
    reparto = await reparto_para_codigo(session, solicitud, firmante)
    return await _mandar(session, solicitud, firmante, reparto, mensaje)

async def enviar_documento_firmado(
    session: AsyncSession,
    solicitud: SolicitudFirma,
    firmantes: list[Firmante],
    contenido_pdf: bytes,
) -> int:
    """Manda el PDF sellado a cada firmante por el canal por el que se le
    pidió la firma. Devuelve a cuántos.

    Nunca lanza: el documento ya está firmado y guardado, y que no llegue una
    copia no puede deshacer eso — sigue estando en la aplicación.
    """
    mensaje = Mensaje(
        asunto=f"Documento firmado: {solicitud.titulo}",
        texto=(
            f"Ya está firmado por todas las partes: {solicitud.titulo} "
            f"({solicitud.codigo}).\n\nTe adjuntamos la copia sellada."
        ),
        adjuntos=(
            Adjunto(
                nombre_archivo=f"{solicitud.codigo}-firmado.pdf",
                contenido=contenido_pdf,
                content_type="application/pdf",
            ),
        ),
        variables=(solicitud.titulo, solicitud.codigo),
    )

    enviados = 0
    for firmante in firmantes:
        canales = [Canal(c) for c in (firmante.canales_envio or [])]
        if not canales:
            canales = await canales_posibles(session, solicitud, firmante)
        try:
            await _mandar(session, solicitud, firmante, _Reparto(canales, []), mensaje)
            enviados += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "No se pudo mandar el firmado de %s a %s: %s",
                solicitud.codigo, firmante.email, exc,
            )
    return enviados


async def avisar_firmantes(
    session: AsyncSession,
    solicitud: SolicitudFirma,
    firmantes: list[Firmante],
    *,
    quien_acaba_de_firmar: Firmante | None = None,
) -> int:
    """Avisa a quienes YA han firmado de que el documento ha avanzado, tanto
    en una firma parcial como al completarse. Devuelve a cuántos se avisó.

    Solo a los que ya firmaron: quien todavía no lo ha hecho tiene su enlace
    y recibir «ha firmado otro» solo es ruido. A quien acaba de firmar
    tampoco — se lo acaba de decir la pantalla.

    Va por el canal por el que se le mandó el enlace a cada uno: si a alguien
    se le pidió la firma por WhatsApp, el aviso por correo probablemente no
    lo vea. Si no consta canal (firmas anteriores a esto), se prueba por
    donde se pueda.

    Nunca lanza: el aviso es cortesía, y un proveedor caído no puede tumbar
    una firma que ya es válida y está guardada.
    """
    firmados = [f for f in firmantes if f.estado == EstadoFirmante.FIRMADA]
    pendientes = [f for f in firmantes if f.estado in _ESTADOS_ABIERTOS]
    cerrado = solicitud.estado == EstadoFirma.FIRMADA

    destinatarios = [
        f
        for f in firmados
        if quien_acaba_de_firmar is None or f.id != quien_acaba_de_firmar.id
    ]
    if not destinatarios:
        return 0

    if cerrado:
        asunto = f"Documento completado: {solicitud.titulo}"
        estado_texto = (
            "Ya está firmado por todas las partes. Quien te lo envió puede "
            "facilitarte la copia sellada con todas las firmas."
        )
        estado_html = (
            "<p>El documento ya está <strong>firmado por todas las partes</strong>. "
            "Quien te lo envió puede facilitarte la copia sellada con todas las firmas.</p>"
        )
    else:
        nombres = ", ".join(f.nombre for f in pendientes)
        asunto = f"Avance de firmas: {solicitud.titulo}"
        estado_texto = (
            f"Ya han firmado {len(firmados)} de {len(firmantes)}. Queda pendiente: {nombres}."
        )
        estado_html = (
            f"<p>Ya han firmado {len(firmados)} de {len(firmantes)}. "
            f"Queda pendiente: <strong>{nombres}</strong>.</p>"
        )

    avisados = 0
    for firmante in destinatarios:
        mensaje = Mensaje(
            asunto=asunto,
            texto=(
                f"Hola {firmante.nombre}:\n\n"
                f"Sobre el documento {solicitud.titulo} ({solicitud.codigo}), que ya "
                f"firmaste.\n\n{estado_texto}\n\nNo hace falta que hagas nada."
            ),
            html=(
                f"<p>Hola {firmante.nombre},</p>"
                f"<p>Te informamos sobre el documento "
                f"<strong>{solicitud.titulo}</strong> ({solicitud.codigo}), que ya firmaste.</p>"
                f"{estado_html}"
                f"<p style='color:#666;font-size:12px'>No hace falta que hagas nada.</p>"
            ),
            variables=(firmante.nombre, solicitud.titulo, estado_texto),
        )
        # Por donde se le pidió la firma. Sin constancia, por lo que haya.
        canales = [Canal(c) for c in (firmante.canales_envio or [])]
        if not canales:
            canales = await canales_posibles(session, solicitud, firmante)
        try:
            await _mandar(
                session, solicitud, firmante, _Reparto(canales, []), mensaje
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Fallo al avisar a %s de %s: %s", firmante.email, solicitud.codigo, exc
            )
            continue
        firmante.ultimo_aviso_en = datetime.now(UTC)
        avisados += 1

    await session.flush()
    return avisados
