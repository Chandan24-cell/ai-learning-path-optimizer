from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, event

from app import models_db  # noqa: F401 - imports all mapped tables
from app.config import settings
from app.database import Base

config = context.config
database_url = settings.database_url.replace("%", "%%")
if config.get_main_option("sqlalchemy.url") == "driver://ignored":
    config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    migration_engine = create_engine(config.get_main_option("sqlalchemy.url"), future=True)
    if migration_engine.dialect.name == "sqlite":

        @event.listens_for(migration_engine, "connect")
        def _enable_sqlite_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    try:
        with migration_engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
