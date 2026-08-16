"""Qué organizaciones puede LEER un principal en los maestros compartibles
(terceros, catálogo, cuadro de precios) — Fase 15.

Vive en `app.core` (no en `app.modules.core`) porque lo consultan los
servicios de terceros/catalogo/presupuestos, y ningún módulo de negocio debe
depender de otro módulo de negocio salvo las dependencias ya explícitas del
grafo de módulos (`depends_on` en el registro). SQL crudo en vez de los
modelos ORM de `app.modules.core.models` por el mismo motivo: evita que este
paquete tenga que importar ese módulo.

Uso EXCLUSIVO de listados/lecturas de maestros — nunca de altas, ediciones o
borrados, que siguen atribuyéndose y limitándose siempre a la organización
propia (`require_organization_id()`). El RLS de las tablas compartibles
(`app/core/rls.py`, `activar_rls_maestro`) es el cortafuegos de verdad: esta
función solo decide qué le PIDE la aplicación a la base de datos, nunca qué
le deja LEER u ESCRIBIR — eso lo decide la política RLS, que nunca amplía el
`WITH CHECK` de escritura por mucho que esta función devuelva.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def organizaciones_visibles(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[uuid.UUID]:
    """La propia organización siempre; además las hermanas de su misma
    cuenta SI esa cuenta tiene `compartir_maestros` activo."""
    fila = (
        await session.execute(
            text(
                "SELECT o.cuenta_id, c.compartir_maestros "
                "FROM core.organization o JOIN core.cuenta c ON c.id = o.cuenta_id "
                "WHERE o.id = :org_id"
            ),
            {"org_id": str(organization_id)},
        )
    ).first()
    if fila is None or not fila.compartir_maestros:
        return [organization_id]

    filas = await session.execute(
        text("SELECT id FROM core.organization WHERE cuenta_id = :cuenta_id"),
        {"cuenta_id": str(fila.cuenta_id)},
    )
    return [row[0] for row in filas.all()]
