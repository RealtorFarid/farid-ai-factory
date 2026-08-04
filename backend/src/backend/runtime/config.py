"""Application configuration.

All settings are read from the environment (or a local ``.env``) with the
``PROPILOT_`` prefix. Nothing in the codebase should read ``os.environ``
directly — go through :func:`get_settings` instead.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from backend import APP_NAME, __version__

Environment = Literal["development", "staging", "production"]
LogFormat = Literal["json", "console"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Runtime configuration, validated once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="PROPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Fields with a validation_alias (openai_api_key) must still be
        # constructible by their Python name — the test suite relies on it.
        populate_by_name=True,
    )

    # ---- Application -----------------------------------------------------
    app_name: str = APP_NAME
    version: str = __version__
    environment: Environment = "development"
    debug: bool = False

    # ---- HTTP server -----------------------------------------------------
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    request_id_header: str = "X-Request-ID"

    # ---- Logging ---------------------------------------------------------
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "console"

    # ---- LLM -------------------------------------------------------------
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("PROPILOT_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    default_model: str = "openai:gpt-5"
    #: Extraction is the highest-volume LLM call in the product, so it gets
    #: its own routing slot: the cheapest model that passes the eval bar.
    #: Falls back to default_model when unset.
    extraction_model: str | None = None
    agent_timeout_seconds: float = Field(default=120.0, gt=0)
    max_prompt_chars: int = Field(default=20_000, gt=0)

    # ---- Persistence -----------------------------------------------------
    # Unset means run entirely in memory: useful for tests, demos and the
    # e2e suite. Set it and the same protocols are served from Postgres.
    database_url: str | None = None
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)
    #: Single-tenant until the account system lands; every row is scoped by it
    #: from day one so multi-tenancy is not a migration later.
    default_org_id: str = "org_default"

    # ---- Tracing ---------------------------------------------------------
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # ---- Validators ------------------------------------------------------

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string as well as a real list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _check_production_hardening(self) -> Settings:
        if self.environment == "production":
            if self.debug:
                raise ValueError("debug must be disabled in production")
            if "*" in self.cors_origins:
                raise ValueError("wildcard CORS origin is not allowed in production")
        return self

    # ---- Derived ---------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def docs_enabled(self) -> bool:
        """Expose OpenAPI docs everywhere except production."""
        return not self.is_production

    @property
    def llm_configured(self) -> bool:
        return self.openai_api_key is not None

    @property
    def persistence_enabled(self) -> bool:
        return bool(self.database_url)

    @property
    def tracing_enabled(self) -> bool:
        return self.langfuse_public_key is not None and self.langfuse_secret_key is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that validation happens exactly once. Tests can reset it with
    ``get_settings.cache_clear()``.
    """
    return Settings()
