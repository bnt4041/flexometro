"""Motor de patrones de numeración de documentos — Fase 16.

Vive en `app.core` (no en `app.modules.core`) por el mismo motivo que
`app.core.visibilidad`: lo consultan los servicios de presupuestos,
facturación y compras, y ningún módulo de negocio debe depender de otro
módulo de negocio salvo las dependencias ya explícitas del grafo de
módulos. `core.organization`/`core.cuenta` se consultan con SQL crudo (sin
RLS, ver `app.core.visibilidad`) para no importar sus modelos ORM; los
modelos propios de este motor (`PatronNumeracion`/`ContadorDocumento`) SÍ
hace falta importarlos para el `INSERT ... ON CONFLICT` del contador, pero
en import diferido (dentro de la función, no a nivel de módulo) — igual
que ya hace `StubAuthBackend` en `app/core/auth.py`: importar
`app.modules.core.numeracion_models` a nivel de módulo obligaría a Python a
inicializar el paquete `app.modules.core` entero (su `__init__.py` importa
`router.py`, que importa los routers que a su vez importan este módulo) —
exactamente el ciclo que ya rompió `app/core/mailer.py` una vez en esta
misma fase.

Cubre el `codigo` interno de Presupuesto, Albarán y Factura por igual — los
tres son un correlativo propio sin significado fiscal (ver el docstring de
`Factura` en `facturacion/models.py`: "serie + numero son la numeración
legal", `codigo` es aparte). Este motor NUNCA toca `Factura.serie`/
`Factura.numero`: esos siguen las reglas de Veri*Factu/Facturae de la
Fase 8 (correlativo por organización+serie, nunca se reutiliza, ver
`facturacion/service.py::emitir_factura`), fuera del alcance de esta fase.
"""

import re
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.core.numeracion_models import PatronNumeracion

# Patrones de fábrica: los mismos formatos que ya se usaban antes de esta
# fase (PRE00001, ALB00001, FAC00001), para que una cuenta sin fila propia
# en `patron_numeracion` (no debería pasar si se sembró al crearla, pero es
# la red de seguridad) se comporte exactamente igual que antes de que
# existiera esta configuración.
PATRON_POR_DEFECTO: dict[str, str] = {
    "presupuesto": "PRE{SEQ:05d}",
    "albaran": "ALB{SEQ:05d}",
    "factura": "FAC{SEQ:05d}",
}

_TOKEN_RE = re.compile(r"\{(SEQ|YYYY|YY|MM|DD|ORG)(?::0(\d+)d)?\}")


class PatronInvalido(Exception):
    pass


def renderizar_patron(
    patron: str, *, fecha: date, org_slug: str, secuencia: int
) -> str:
    def _sustituir(m: re.Match) -> str:
        token, ancho = m.group(1), m.group(2)
        if token == "SEQ":
            return str(secuencia).zfill(int(ancho)) if ancho else str(secuencia)
        if token == "YYYY":
            return f"{fecha.year:04d}"
        if token == "YY":
            return f"{fecha.year % 100:02d}"
        if token == "MM":
            return f"{fecha.month:02d}"
        if token == "DD":
            return f"{fecha.day:02d}"
        assert token == "ORG"
        return org_slug

    return _TOKEN_RE.sub(_sustituir, patron)


def validar_patron(patron: str) -> None:
    if not patron.strip():
        raise PatronInvalido("El patrón no puede estar vacío")
    tokens_desconocidos = re.findall(r"\{([A-Z]+)[^}]*\}", patron)
    validos = {"SEQ", "YYYY", "YY", "MM", "DD", "ORG"}
    for token in tokens_desconocidos:
        if token not in validos:
            raise PatronInvalido(f"Token desconocido: {{{token}}}")
    if "{SEQ" not in patron:
        raise PatronInvalido("El patrón debe incluir {SEQ} (o cada documento repetiría el código)")
    # Se prueba a renderizar con valores de ejemplo — cualquier fallo de
    # formato (p.ej. {SEQ:0Xd} con X no numérico) sale ahora, no al crear
    # el primer documento real con este patrón.
    renderizar_patron(patron, fecha=date.today(), org_slug="demo", secuencia=1)


async def _cuenta_y_slug(session: AsyncSession, organization_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    fila = (
        await session.execute(
            text("SELECT cuenta_id, slug FROM core.organization WHERE id = :org_id"),
            {"org_id": str(organization_id)},
        )
    ).first()
    if fila is None:
        raise LookupError(f"La organización {organization_id} no existe")
    return fila.cuenta_id, fila.slug


async def _obtener_patron(
    session: AsyncSession, cuenta_id: uuid.UUID, tipo_documento: str
) -> "PatronNumeracion | None":
    from app.modules.core.numeracion_models import PatronNumeracion  # ver docstring del módulo

    return await session.scalar(
        select(PatronNumeracion).where(
            PatronNumeracion.cuenta_id == cuenta_id, PatronNumeracion.tipo_documento == tipo_documento
        )
    )


async def _siguiente_secuencia(
    session: AsyncSession, *, ambito_id: uuid.UUID, tipo_documento: str
) -> int:
    """Incrementa atómicamente el contador de (ámbito, tipo) y devuelve el
    nuevo valor — INSERT ... ON CONFLICT DO UPDATE, no un SELECT+UPDATE
    separado, para que dos altas simultáneas nunca puedan llevarse el mismo
    número."""
    from app.modules.core.numeracion_models import ContadorDocumento  # ver docstring del módulo

    stmt = (
        pg_insert(ContadorDocumento)
        .values(id=uuid.uuid4(), ambito_id=ambito_id, tipo_documento=tipo_documento, ultimo=1)
        .on_conflict_do_update(
            index_elements=["ambito_id", "tipo_documento"],
            set_={"ultimo": ContadorDocumento.ultimo + 1},
        )
        .returning(ContadorDocumento.ultimo)
    )
    return (await session.execute(stmt)).scalar_one()


async def siguiente_referencia(
    session: AsyncSession, *, organization_id: uuid.UUID, tipo_documento: str
) -> str:
    """El `codigo` interno completo, listo para guardar en el documento
    nuevo (Presupuesto, Albarán o Factura — nunca `serie`/`numero`, ver
    docstring del módulo)."""
    cuenta_id, org_slug = await _cuenta_y_slug(session, organization_id)
    fila = await _obtener_patron(session, cuenta_id, tipo_documento)
    patron = fila.patron if fila else PATRON_POR_DEFECTO[tipo_documento]
    compartida = bool(fila.secuencia_compartida) if fila else False
    ambito_id = cuenta_id if compartida else organization_id
    secuencia = await _siguiente_secuencia(session, ambito_id=ambito_id, tipo_documento=tipo_documento)
    return renderizar_patron(patron, fecha=date.today(), org_slug=org_slug, secuencia=secuencia)
