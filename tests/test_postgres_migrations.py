from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.postgres


def test_migrations_run_on_dedicated_postgresql_database() -> None:
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to the disposable learning_path_test database")
    if urlsplit(database_url).path.lstrip("/") != "learning_path_test":
        pytest.fail("Refusing to migrate a database not named learning_path_test")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert "alembic_version" in inspector.get_table_names()
        assert "question_sessions" in inspector.get_table_names()
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert revision == "0006_rule_based_quizzes"
    finally:
        engine.dispose()
