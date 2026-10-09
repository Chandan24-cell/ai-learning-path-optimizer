from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    ("database_url", "expected_url"),
    [
        ("postgres://db.example/learning_path", "postgresql+psycopg://db.example/learning_path"),
        (
            "postgresql://db.example/learning_path",
            "postgresql+psycopg://db.example/learning_path",
        ),
    ],
)
def test_production_settings_normalize_render_postgres_url(
    database_url: str, expected_url: str
) -> None:
    settings = Settings(
        app_env="production",
        app_secret="private-test-secret-with-more-than-32-characters",
        database_url=database_url,
        allowed_origins=["https://learning-path.example"],
        _env_file=None,
    )
    assert settings.database_url == expected_url


@pytest.mark.parametrize(
    "origins",
    [[], ["http://learning-path.example"], ["https://localhost:8000"]],
)
def test_production_rejects_missing_or_insecure_origins(origins: list[str]) -> None:
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS"):
        Settings(
            app_env="production",
            app_secret="private-test-secret-with-more-than-32-characters",
            allowed_origins=origins,
            _env_file=None,
        )
