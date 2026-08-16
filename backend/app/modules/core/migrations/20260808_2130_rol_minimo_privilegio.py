"""core: rol de mínimo privilegio para la API en tiempo de ejecución

La imagen oficial de Postgres crea POSTGRES_USER como superusuario, y un
superusuario se salta RLS siempre, sin importar FORCE ROW LEVEL SECURITY: esa
cláusula solo afecta al propietario de la tabla cuando no es superusuario. Si
la API se conectara con ese rol, las políticas de la migración anterior serían
papel mojado — que es exactamente lo que pasó al verificarlo con dos
organizaciones y datos reales.

Esta migración crea `app_db_user` (por defecto `obras_app`) sin SUPERUSER y sin
BYPASSRLS, le concede lo mínimo para operar (uso de los esquemas, DML sobre las
tablas) y añade privilegios por defecto para que las migraciones futuras —que
siguen ejecutándose con el rol admin— no tengan que repetir el GRANT cada vez
que crean una tabla nueva.

Revision ID: core_0003
Revises: core_0002
Create Date: 2026-08-08
"""
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings

revision: str = "core_0003"
down_revision: str | None = "core_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESQUEMAS = ("core", "terceros", "catalogo", "presupuestos")

# El nombre de rol se interpola en SQL como identificador —no se puede pasar
# como bind param—, así que se valida contra inyección aunque venga de una
# variable de entorno propia y no de un usuario final.
_RE_IDENTIFICADOR = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validar_identificador(nombre: str, etiqueta: str) -> str:
    if not _RE_IDENTIFICADOR.match(nombre):
        raise ValueError(
            f"{etiqueta} '{nombre}' no es un identificador de PostgreSQL válido"
        )
    return nombre


def _literal_sql(valor: str) -> str:
    """Literal de cadena para SQL, con las comillas simples escapadas.

    CREATE ROLE / ALTER ROLE son sentencias DDL: Postgres no admite parámetros
    ligados ($1) en ellas —ni siquiera dentro de un bloque DO, donde además el
    cuerpo entre los delimitadores $$ es texto literal para el analizador y un
    ":password" ahí dentro nunca llegaría a sustituirse—, así que el valor se
    interpola ya escapado, como se hace habitualmente para este tipo de DDL.
    """
    return "'" + valor.replace("'", "''") + "'"


def upgrade() -> None:
    settings = get_settings()
    rol = _validar_identificador(settings.app_db_user, "APP_DB_USER")
    if not settings.app_db_password:
        raise RuntimeError(
            "APP_DB_PASSWORD no está definida: hace falta para crear el rol de "
            "mínimo privilegio con el que se conecta la API"
        )
    admin = _validar_identificador(settings.postgres_user, "POSTGRES_USER")

    contrasena = _literal_sql(settings.app_db_password)
    conexion = op.get_bind()
    existe = conexion.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :rol"), {"rol": rol}
    ).first()

    if existe is None:
        op.execute(
            f"CREATE ROLE {rol} LOGIN PASSWORD {contrasena} "
            "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION"
        )
    else:
        # Migración reejecutada, o rol creado a mano: se deja la contraseña
        # sincronizada con la que declara el entorno en vez de fallar.
        op.execute(f"ALTER ROLE {rol} LOGIN PASSWORD {contrasena}")

    for esquema in ESQUEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {esquema} TO {rol}")
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {esquema} TO {rol}"
        )
        op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {esquema} TO {rol}")

        # Privilegios por defecto: las tablas que una migración futura cree
        # con el rol admin quedan accesibles para el rol de aplicación sin
        # repetir este GRANT en cada migración nueva. Queda registrado en el
        # catálogo, no es un ajuste de sesión.
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {esquema} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {rol}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {esquema} "
            f"GRANT USAGE ON SEQUENCES TO {rol}"
        )


def downgrade() -> None:
    settings = get_settings()
    rol = _validar_identificador(settings.app_db_user, "APP_DB_USER")
    admin = _validar_identificador(settings.postgres_user, "POSTGRES_USER")

    for esquema in ESQUEMAS:
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {esquema} "
            f"REVOKE ALL ON TABLES FROM {rol}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {esquema} "
            f"REVOKE ALL ON SEQUENCES FROM {rol}"
        )
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {esquema} FROM {rol}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {esquema} FROM {rol}")
        op.execute(f"REVOKE USAGE ON SCHEMA {esquema} FROM {rol}")

    # No es propietario de nada, así que se puede borrar sin más.
    op.execute(f"DROP ROLE IF EXISTS {rol}")
