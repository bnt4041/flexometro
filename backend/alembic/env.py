import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.models import Base
from app.modules import import_models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Todos los modelos deben estar importados antes de leer Base.metadata,
# o el autogenerate propondría borrar las tablas que no ha visto.
import_models()
target_metadata = Base.metadata

settings = get_settings()


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Ignora lo que no pertenece a los schemas de los módulos."""
    if type_ == "table" and obj.schema in (None, "public"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # El rol admin de las migraciones se llama `obras`, igual que el schema
    # del módulo de ejecución de obra: por esa coincidencia de nombres,
    # `search_path = "$user", public` mete ese schema en la ruta de búsqueda
    # nada más conectar. SQLAlchemy cachea `default_schema_name` en el primer
    # connect y no lo vuelve a mirar, así que un `SET search_path` posterior
    # en la misma conexión no sirve de nada — hay que fijarlo en el propio
    # connect, con `server_settings`, para que el dialecto lo vea desde la
    # primera consulta. Sin esto, autogenerate confunde el schema `obras` con
    # el esquema por defecto y propone desfases que no existen. Toda la
    # aplicación referencia sus tablas con el schema explícito de todas
    # formas, así que fijarlo a "public" no cambia ningún comportamiento real.
    engine = create_async_engine(
        settings.database_url,
        poolclass=None,
        connect_args={"server_settings": {"search_path": "public"}},
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
