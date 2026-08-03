"""Configuration loading, parsing and production hardening."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.runtime.config import Settings, get_settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type, call-arg]


def test_defaults_are_development_safe() -> None:
    cfg = _settings()
    assert cfg.environment == "development"
    assert cfg.is_production is False
    assert cfg.docs_enabled is True
    assert cfg.port == 8000


def test_env_prefix_is_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPILOT_PORT", "9123")
    monkeypatch.setenv("PROPILOT_LOG_FORMAT", "json")
    cfg = _settings()
    assert cfg.port == 9123
    assert cfg.log_format == "json"


def test_cors_origins_accepts_comma_separated_string() -> None:
    cfg = _settings(cors_origins="http://a.test, http://b.test ,")
    assert cfg.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_origins_accepts_a_list() -> None:
    assert _settings(cors_origins=["http://a.test"]).cors_origins == ["http://a.test"]


def test_openai_key_falls_back_to_unprefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROPILOT_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-plain-env")
    cfg = _settings()
    assert cfg.llm_configured is True
    assert cfg.openai_api_key is not None
    assert cfg.openai_api_key.get_secret_value() == "sk-from-plain-env"


def test_prefixed_key_wins_over_unprefixed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-plain")
    monkeypatch.setenv("PROPILOT_OPENAI_API_KEY", "sk-prefixed")
    cfg = _settings()
    assert cfg.openai_api_key is not None
    assert cfg.openai_api_key.get_secret_value() == "sk-prefixed"


def test_secret_is_not_leaked_by_repr() -> None:
    cfg = _settings(openai_api_key="sk-super-secret")
    assert "sk-super-secret" not in repr(cfg)
    assert "sk-super-secret" not in str(cfg.openai_api_key)


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="debug must be disabled in production"):
        _settings(environment="production", debug=True)


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="wildcard CORS origin"):
        _settings(environment="production", cors_origins="*")


def test_production_hides_docs() -> None:
    cfg = _settings(environment="production", cors_origins="https://app.test")
    assert cfg.docs_enabled is False
    assert cfg.is_production is True


def test_port_must_be_in_range() -> None:
    with pytest.raises(ValidationError):
        _settings(port=0)


def test_tracing_requires_both_keys() -> None:
    assert _settings(langfuse_public_key="pk").tracing_enabled is False
    assert _settings(langfuse_public_key="pk", langfuse_secret_key="sk").tracing_enabled is True


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings() is get_settings()
    finally:
        get_settings.cache_clear()
