"""Configuration handling."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Environment, LLMProvider, Settings


def _settings(**overrides: object) -> Settings:
    """Build settings without reading the developer's .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_defaults_are_development_and_sqlite() -> None:
    settings = _settings()
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.is_development
    assert settings.database_url.startswith("sqlite")
    assert settings.port == 8000


def test_llm_defaults_are_openrouter_deepseek() -> None:
    settings = _settings()
    assert settings.llm_provider is LLMProvider.OPENROUTER
    assert settings.llm_model == "deepseek/deepseek-chat"


def test_llm_curriculum_proposal_limits_are_removed() -> None:
    settings = _settings()
    assert not hasattr(settings, "curriculum_max_sections")
    assert not hasattr(settings, "curriculum_section_char_budget")


def test_anthropic_and_openai_providers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(llm_provider="anthropic")
    with pytest.raises(ValidationError):
        _settings(llm_provider="openai")


def test_llm_is_not_configured_without_a_key() -> None:
    settings = _settings(llm_provider=LLMProvider.OPENROUTER, llm_api_key=None)
    assert settings.llm_configured is False
    assert "no API key configured" in settings.describe_llm()


def test_llm_is_configured_with_provider_and_key() -> None:
    settings = _settings(llm_provider=LLMProvider.OPENROUTER, llm_api_key="sk-test-123")
    assert settings.llm_configured is True


def test_llm_provider_none_is_never_configured() -> None:
    settings = _settings(llm_provider=LLMProvider.NONE, llm_api_key="sk-test-123")
    assert settings.llm_configured is False
    assert "disabled" in settings.describe_llm()


def test_describe_llm_never_leaks_the_key() -> None:
    secret = "sk-super-secret-value"
    settings = _settings(llm_provider=LLMProvider.OPENROUTER, llm_api_key=secret)
    assert secret not in settings.describe_llm()
    assert secret not in repr(settings)


def test_blank_env_values_become_none() -> None:
    settings = _settings(llm_api_key="", llm_base_url="   ")
    assert settings.llm_api_key is None
    assert settings.llm_base_url is None


def test_log_level_is_upper_cased() -> None:
    assert _settings(log_level="debug").log_level == "DEBUG"


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    settings = Settings()
    assert settings.environment is Environment.PRODUCTION
    assert settings.is_development is False
    assert settings.port == 9123
    assert settings.llm_model == "some-model"


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(port=0)
