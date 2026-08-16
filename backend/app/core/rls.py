"""Row Level Security y privilegios para migraciones.

Se descubrió en la Fase 6 que un superusuario de PostgreSQL se salta RLS
siempre, sin importar `FORCE ROW LEVEL SECURITY` — por eso la API se conecta
con un rol de mínimo privilegio (`obras_app`) y no con el admin de las
migraciones. `core_0003` le dio permisos por defecto sobre los schemas que
existían entonces (core, terceros, catalogo, presupuestos), de modo que las
tablas nuevas *en esos schemas* quedan accesibles solas.

Un schema completamente nuevo (un módulo que se estrena) es harina de otro
costal: `obras_app` no tiene ni siquiera `USAGE` sobre él hasta que alguien se
lo concede. Por eso `conceder_privilegios_app` existe — la primera migración
de cada módulo nuevo la llama sobre su propio schema, justo después de
crearlo, o el rol de la API se topa con "permission denied for schema X" en
la primera consulta.
"""

import re

from alembic import op

from app.core.config import get_settings

POLITICA = "aislamiento_organizacion"

# NULLIF: sin contexto, `current_setting(..., true)` puede devolver NULL o
# cadena vacía según cómo se dejara la sesión. Con NULLIF los dos casos acaban
# en NULL, la comparación es NULL y no se ve ninguna fila. Falla cerrado.
CONDICION = "organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid"


def activar_rls(schema: str, tabla: str) -> None:
    completo = f"{schema}.{tabla}"
    op.execute(f"ALTER TABLE {completo} ENABLE ROW LEVEL SECURITY")
    # FORCE: sin esto el propietario de la tabla (el rol admin de las
    # migraciones) se saltaría sus propias políticas.
    op.execute(f"ALTER TABLE {completo} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {POLITICA} ON {completo}
            USING ({CONDICION})
            WITH CHECK ({CONDICION})
        """
    )


def desactivar_rls(schema: str, tabla: str) -> None:
    completo = f"{schema}.{tabla}"
    op.execute(f"DROP POLICY IF EXISTS {POLITICA} ON {completo}")
    op.execute(f"ALTER TABLE {completo} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {completo} DISABLE ROW LEVEL SECURITY")


# --- Maestros compartibles entre organizaciones de una cuenta (Fase 15) ---
#
# Terceros, catálogo y cuadro de precios pueden hacerse visibles entre las
# organizaciones de una misma cuenta si esta activa `compartir_maestros`
# (ver `app.core.visibilidad`) — pero SOLO para leer. Un único policy
# `FOR ALL` con un USING ampliado NO sirve para esto: en Postgres, USING
# también decide qué filas puede TOCAR un UPDATE/DELETE, así que ampliarlo
# ampliaría igual de qué se puede BORRAR — con `compartir_maestros` activo,
# un DELETE crudo (sin pasar por la aplicación) podría borrar la fila de
# una organización hermana. La única forma correcta es una política por
# comando: SELECT con USING ampliado, e INSERT/UPDATE/DELETE con USING y
# WITH CHECK estrictos (ver `references/postgresql-rls` — confirmado contra
# la documentación oficial: SELECT no acepta WITH CHECK, INSERT no acepta
# USING, y las políticas de distinto FOR no se combinan entre comandos).
CONDICION_MAESTRO_COMPARTIDO = f"""(
    {CONDICION}
    OR organization_id IN (
        SELECT o2.id
        FROM core.organization o1
        JOIN core.organization o2 ON o2.cuenta_id = o1.cuenta_id
        JOIN core.cuenta c ON c.id = o1.cuenta_id
        WHERE o1.id = NULLIF(current_setting('app.organization_id', true), '')::uuid
          AND c.compartir_maestros
    )
)"""

_POLITICA_SELECT = f"{POLITICA}_select"
_POLITICA_INSERT = f"{POLITICA}_insert"
_POLITICA_UPDATE = f"{POLITICA}_update"
_POLITICA_DELETE = f"{POLITICA}_delete"


def activar_rls_maestro(schema: str, tabla: str) -> None:
    """Igual que `activar_rls`, para una tabla que se crea ya como maestro
    compartible desde el principio."""
    completo = f"{schema}.{tabla}"
    op.execute(f"ALTER TABLE {completo} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {completo} FORCE ROW LEVEL SECURITY")
    _crear_politicas_maestro(completo)


def convertir_a_rls_maestro(schema: str, tabla: str) -> None:
    """Sustituye la política estándar (creada con `activar_rls` en una fase
    anterior, un único policy `FOR ALL`) por las cuatro políticas por
    comando — ENABLE/FORCE ya estaban puestos, no hace falta repetirlos."""
    completo = f"{schema}.{tabla}"
    op.execute(f"DROP POLICY IF EXISTS {POLITICA} ON {completo}")
    _crear_politicas_maestro(completo)


def _crear_politicas_maestro(completo: str) -> None:
    op.execute(f"CREATE POLICY {_POLITICA_SELECT} ON {completo} FOR SELECT USING ({CONDICION_MAESTRO_COMPARTIDO})")
    op.execute(f"CREATE POLICY {_POLITICA_INSERT} ON {completo} FOR INSERT WITH CHECK ({CONDICION})")
    op.execute(
        f"CREATE POLICY {_POLITICA_UPDATE} ON {completo} FOR UPDATE USING ({CONDICION}) WITH CHECK ({CONDICION})"
    )
    op.execute(f"CREATE POLICY {_POLITICA_DELETE} ON {completo} FOR DELETE USING ({CONDICION})")


def revertir_rls_maestro(schema: str, tabla: str) -> None:
    """Downgrade de `convertir_a_rls_maestro`: vuelve a la única política
    estándar `FOR ALL`."""
    completo = f"{schema}.{tabla}"
    for politica in (_POLITICA_SELECT, _POLITICA_INSERT, _POLITICA_UPDATE, _POLITICA_DELETE):
        op.execute(f"DROP POLICY IF EXISTS {politica} ON {completo}")
    op.execute(
        f"""
        CREATE POLICY {POLITICA} ON {completo}
            USING ({CONDICION})
            WITH CHECK ({CONDICION})
        """
    )


# El nombre de rol/schema se interpola en SQL como identificador —no se puede
# pasar como bind param en DDL—, así que se valida contra inyección aunque
# venga de la propia configuración y no de un usuario final.
_RE_IDENTIFICADOR = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validar_identificador(nombre: str, etiqueta: str) -> str:
    if not _RE_IDENTIFICADOR.match(nombre):
        raise ValueError(
            f"{etiqueta} '{nombre}' no es un identificador de PostgreSQL válido"
        )
    return nombre


def conceder_privilegios_app(schema: str) -> None:
    """Da al rol de la API acceso a un schema recién creado.

    Sin esto, la primera consulta del rol de mínimo privilegio contra el
    schema nuevo falla con "permission denied for schema" — `core_0003` solo
    concedió esto a los schemas que existían en aquel momento.
    """
    settings = get_settings()
    rol = _validar_identificador(settings.app_db_user, "APP_DB_USER")
    admin = _validar_identificador(settings.postgres_user, "POSTGRES_USER")

    op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {rol}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {rol}"
    )
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {schema} TO {rol}")
    # Para que las migraciones futuras de este mismo schema no tengan que
    # repetir el GRANT en cada tabla nueva.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {schema} "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {rol}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {schema} "
        f"GRANT USAGE ON SEQUENCES TO {rol}"
    )


def revocar_privilegios_app(schema: str) -> None:
    settings = get_settings()
    rol = _validar_identificador(settings.app_db_user, "APP_DB_USER")
    admin = _validar_identificador(settings.postgres_user, "POSTGRES_USER")

    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {schema} "
        f"REVOKE ALL ON TABLES FROM {rol}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA {schema} "
        f"REVOKE ALL ON SEQUENCES FROM {rol}"
    )
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {rol}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM {rol}")
    op.execute(f"REVOKE USAGE ON SCHEMA {schema} FROM {rol}")
