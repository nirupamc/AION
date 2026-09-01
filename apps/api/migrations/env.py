from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure the app package is importable when alembic is run from apps/api.
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.core.config import settings  # noqa: E402
from app.db import Base, _ensure_sqlite_directory  # noqa: E402
# Importing the models module registers the tables on Base.metadata.
import app.models  # noqa: E402,F401

config = context.config

# Override the URL with whatever the app is configured for, so dev/test envs
# stay consistent. (alembic.ini also has a default.)
config.set_main_option("sqlalchemy.url", settings.database_url)
# Ensure the SQLite parent directory exists before Alembic tries to connect,
# so `alembic upgrade head` works from a clean checkout where data/ is missing.
_ensure_sqlite_directory(settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Re-ensure directory in case DATABASE_URL was overridden via env var
    # after the module-level call above (e.g. in tests).
    _ensure_sqlite_directory(config.get_main_option("sqlalchemy.url") or settings.database_url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
