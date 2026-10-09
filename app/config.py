"""Environment-backed application settings."""

from __future__ import annotations

import os
import secrets
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Self, cast

from dotenv import dotenv_values
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEGACY_REJECTED_VALUE_HASH = "b0fb4e0daf79961b834c3560ed618a3a9148bac9db24a76bc9be31198ef4290b"


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret: SecretStr | None = None
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'outputs' / 'app.db'}"
    model_dir: Path = PROJECT_ROOT / "outputs" / "models"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "production"}:
            raise ValueError("APP_ENV must be 'development' or 'production'")
        return normalized

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_postgresql_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.replace("postgres://", "postgresql+psycopg://", 1).replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        return value

    @model_validator(mode="after")
    def validate_production_secret(self) -> Self:
        if self.app_env == "production":
            secret = self.app_secret.get_secret_value() if self.app_secret else ""
            legacy_secret_digest = sha256(secret.encode("utf-8")).hexdigest()
            if len(secret) < 32 or legacy_secret_digest == LEGACY_REJECTED_VALUE_HASH:
                raise ValueError(
                    "Production requires APP_SECRET with at least 32 characters "
                    "and it cannot be the development default"
                )
            if not self.allowed_origins or any(
                "localhost" in origin or "127.0.0.1" in origin
                for origin in self.allowed_origins
            ):
                raise ValueError(
                    "Production requires ALLOWED_ORIGINS with only public HTTPS origins"
                )
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("Production ALLOWED_ORIGINS must use HTTPS")
        if self.access_token_minutes <= 0 or self.refresh_token_days <= 0:
            raise ValueError("Token lifetimes must be positive")
        return self

    @property
    def signing_key(self) -> str:
        """Return configured key; development uses a random process-only key."""
        if self.app_secret:
            return self.app_secret.get_secret_value()
        if self.app_env == "production":  # guarded by validate_production_secret
            raise RuntimeError("APP_SECRET is required in production")
        return _DEVELOPMENT_EPHEMERAL_SECRET


_DEVELOPMENT_EPHEMERAL_SECRET = secrets.token_urlsafe(48)
_mode = os.environ.get("APP_ENV")
if _mode is None:
    _mode = dotenv_values(PROJECT_ROOT / ".env").get("APP_ENV", "development")
_load_dotenv = str(_mode).strip().lower() == "development"
settings: Settings = cast(Any, Settings)(_env_file=PROJECT_ROOT / ".env" if _load_dotenv else None)
