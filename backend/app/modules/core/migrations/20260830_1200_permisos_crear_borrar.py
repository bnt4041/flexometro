"""core: separar «crear» y «borrar» de «editar» en los permisos

Hasta ahora un grupo tenía dos alcances por módulo: ver y editar. «Editar»
llevaba dentro dar de alta y borrar, que no son el mismo riesgo — hay
perfiles enteros (administrativos, encargados) que tienen que poder crear y
modificar sin poder borrar nada.

Las columnas nuevas COPIAN el valor de `editar`, no arrancan vacías: si
nacieran en `ninguno`, al aplicar esto todo el mundo perdería de golpe la
capacidad de crear y borrar que tenía. Nadie se queda fuera y nadie gana
permisos; a partir de aquí, quien quiera restringir lo hace desde el panel.

Revision ID: core_permisos_0001
Revises: core_whatsapp_0001
Create Date: 2026-08-30
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "core_permisos_0001"
down_revision: str | None = "core_whatsapp_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ALCANCE = ("ninguno", "propios", "todos")


def upgrade() -> None:
    for columna, nombre_enum in (("crear", "alcance_crear"), ("borrar", "alcance_borrar")):
        op.add_column(
            "grupo_permiso",
            sa.Column(
                columna,
                sa.Enum(*_ALCANCE, name=nombre_enum, native_enum=False, length=32),
                nullable=False,
                server_default=sa.text("'ninguno'"),
            ),
            schema="core",
        )
    # El estado de HOY: lo que cada grupo podía editar es lo que podía crear
    # y borrar, porque no había forma de distinguirlo.
    op.execute("UPDATE core.grupo_permiso SET crear = editar, borrar = editar")


def downgrade() -> None:
    # No se devuelve nada a `editar`: al volver atrás, crear y borrar vuelven
    # a ser lo mismo que editar por definición.
    op.drop_column("grupo_permiso", "borrar", schema="core")
    op.drop_column("grupo_permiso", "crear", schema="core")
