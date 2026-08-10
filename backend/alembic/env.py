"""
Alembic environment configuration.
Uses SYNCHRONOUS SQLAlchemy engine (psycopg2).
Alembic is a sync tool — do NOT use asyncpg here.
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

# Add the backend directory to sys.path so 'app' package can be imported
# This works regardless of where the 'alembic' command is run from
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.database import Base
# Import ALL models so Alembic autogenerate detects every table
import app.models  # noqa: F401

# Alembic Config object — provides access to alembic.ini values
config = context.config

# Override sqlalchemy.url with SYNC URL from environment (psycopg2, not asyncpg)
config.set_main_option("sqlalchemy.url", settings.POSTGRES_SYNC_URL)

# Configure Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Generates SQL script without connecting to the database.
    Useful for: reviewing migrations before applying, applying to remote DB.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    Connects to the database and applies migrations directly.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
