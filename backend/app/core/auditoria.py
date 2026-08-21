"""Motor de historial de cambios (Fase 38).

Un único listener de sesión de SQLAlchemy, no llamadas explícitas desde cada
servicio: cualquier modelo con `AutoriaMixin` (las entidades raíz de cada
módulo — ver su docstring) queda auditado automáticamente en cuanto se crea,
se modifica o se borra, sin que el autor del módulo tenga que acordarse de
nada. Mismo principio que RLS: seguro por defecto, no opt-in por endpoint.

Se registra sobre `sqlalchemy.orm.Session` (la síncrona), no sobre
`AsyncSession`: `AsyncSession` delega en una `Session` de verdad por debajo
(`.sync_session`) y es ahí donde SQLAlchemy dispara `before_flush` — es el
mismo patrón que usa la propia documentación de SQLAlchemy para "object
history"/versionado.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from app.core.models import AutoriaMixin
from app.core.tenancy import current_principal

# `updated_at`/`created_at` cambian en CADA escritura (server_default/onupdate):
# listarlos como "cambio" en cada modificación sería ruido puro, no información.
_COLUMNAS_IGNORADAS = {"created_at", "updated_at"}


def tabla_de(modelo: type) -> str:
    """'schema.tabla' de un modelo mapeado — la misma cadena que graba el
    listener, para que los endpoints de lectura (`auditoria_service`) nunca
    puedan escribirla a mano y desincronizarse."""
    tabla = modelo.__table__
    return f"{tabla.schema}.{tabla.name}"


def _serializable(valor: object) -> object:
    """JSONB no serializa Decimal/UUID/date/Enum solos: se convierten aquí,
    no al escribir, para que el valor guardado sea siempre JSON-plano."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (uuid.UUID,)):
        return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, (str, int, float, bool)):
        return valor
    # Tipos compuestos (listas/dicts de JSONB, por ejemplo `Organization.settings`
    # si algún día llevara AutoriaMixin): se guardan tal cual, ya son JSON-planos.
    return valor


def _fila_auditoria(obj, accion, cambios, organization_id, usuario_subject, usuario_nombre):
    from app.modules.core.auditoria_models import RegistroAuditoria

    return RegistroAuditoria(
        organization_id=organization_id,
        tabla=tabla_de(type(obj)),
        registro_id=obj.id,
        accion=accion,
        cambios=cambios,
        usuario_subject=usuario_subject,
        usuario_nombre=usuario_nombre,
    )


@event.listens_for(Session, "before_flush")
def _auditar_antes_de_flush(session: Session, flush_context, instances) -> None:
    from app.modules.core.auditoria_models import AccionAuditoria

    principal = current_principal()
    usuario_subject = principal.subject if principal else None
    usuario_nombre = principal.username if principal else None

    filas = []

    for obj in list(session.new):
        if not isinstance(obj, AutoriaMixin):
            continue
        org_id = getattr(obj, "organization_id", None)
        if org_id is None:
            continue
        # `UUIDPrimaryKeyMixin.id` tiene `default=uuid.uuid4`, pero antes de
        # `before_flush` SQLAlchemy todavía no lo ha aplicado — sin esto la
        # fila de auditoría se insertaría con `registro_id` a NULL.
        if obj.id is None:
            obj.id = uuid.uuid4()
        filas.append(
            _fila_auditoria(
                obj, AccionAuditoria.CREADO, None, org_id, usuario_subject, usuario_nombre
            )
        )

    for obj in list(session.dirty):
        if not isinstance(obj, AutoriaMixin):
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        org_id = getattr(obj, "organization_id", None)
        if org_id is None:
            continue

        cambios = []
        mapper = inspect(obj).mapper
        for attr in mapper.column_attrs:
            if attr.key in _COLUMNAS_IGNORADAS:
                continue
            historial = get_history(obj, attr.key)
            if not historial.has_changes():
                continue
            antes = historial.deleted[0] if historial.deleted else None
            despues = historial.added[0] if historial.added else getattr(obj, attr.key)
            if antes == despues:
                continue
            cambios.append(
                {
                    "campo": attr.key,
                    "antes": _serializable(antes),
                    "despues": _serializable(despues),
                }
            )
        if not cambios:
            continue
        filas.append(
            _fila_auditoria(
                obj, AccionAuditoria.MODIFICADO, cambios, org_id, usuario_subject, usuario_nombre
            )
        )

    for obj in list(session.deleted):
        if not isinstance(obj, AutoriaMixin):
            continue
        org_id = getattr(obj, "organization_id", None)
        if org_id is None:
            continue
        filas.append(
            _fila_auditoria(
                obj, AccionAuditoria.ELIMINADO, None, org_id, usuario_subject, usuario_nombre
            )
        )

    for fila in filas:
        session.add(fila)
