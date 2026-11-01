"""The providers the app can call, and what each needs (ADR-068).

Every provider here speaks the OpenAI chat API, so one client serves them all
(``app.llm.client``): a provider is an endpoint, a key, default models, and a few quirks.
Claude is reached through Anthropic's OpenAI-compatible endpoint; ``custom`` is any other
OpenAI-compatible URL (a local vLLM or Ollama, a lab gateway).

Each provider's URL, key and default model come from ``.env`` and can be replaced from the
Settings screen (``app.settings_store.provider_configs``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import SecretStr

from app.config import LLMProvider, Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: How a provider's model list is read: an OpenAI-style ``GET /models``, Anthropic's own
#: ``/v1/models``, or not at all (Azure lists deployments only through its management API).
ModelListing = Literal["openai", "anthropic", "none"]


@dataclass(frozen=True)
class ProviderSpec:
    id: LLMProvider
    label: str
    #: ``None`` when the endpoint is the account's own and has to be entered (Azure, custom).
    base_url: str | None
    #: The chat model a role uses when the provider is chosen and no model is.
    chat_model: str | None
    #: The embedding model it offers by default; ``None`` when it offers none to default to.
    embedding_model: str | None
    #: Whether a role can embed with it at all (custom: if its endpoint does).
    embeds: bool
    listing: ModelListing
    #: Claude through the compatibility endpoint ignores ``response_format`` and fences its
    #: JSON, so structured calls ask for fenced JSON instead of JSON mode.
    fenced_json: bool = False


def _specs(env: Settings) -> dict[LLMProvider, ProviderSpec]:
    return {
        spec.id: spec
        for spec in (
            ProviderSpec(
                LLMProvider.OPENROUTER,
                "OpenRouter",
                OPENROUTER_BASE_URL,
                env.llm_model,
                env.embedding_model,
                embeds=True,
                listing="openai",
            ),
            ProviderSpec(
                LLMProvider.AZURE,
                "Azure OpenAI",
                None,
                env.azure_model,
                env.azure_embedding_model,
                embeds=True,
                listing="none",
            ),
            ProviderSpec(
                LLMProvider.OPENAI,
                "OpenAI",
                "https://api.openai.com/v1",
                "gpt-5-mini",
                "text-embedding-3-small",
                embeds=True,
                listing="openai",
            ),
            ProviderSpec(
                LLMProvider.ANTHROPIC,
                "Anthropic (Claude)",
                "https://api.anthropic.com/v1/",
                "claude-haiku-4-5",
                None,
                embeds=False,
                listing="anthropic",
                fenced_json=True,
            ),
            ProviderSpec(
                LLMProvider.XAI,
                "xAI (Grok)",
                "https://api.x.ai/v1",
                "grok-4",
                None,
                embeds=False,
                listing="openai",
            ),
            ProviderSpec(
                LLMProvider.DEEPSEEK,
                "DeepSeek",
                "https://api.deepseek.com/v1",
                "deepseek-chat",
                None,
                embeds=False,
                listing="openai",
            ),
            ProviderSpec(
                LLMProvider.CUSTOM,
                "Custom (OpenAI-compatible)",
                None,
                env.custom_model,
                None,
                embeds=True,
                listing="openai",
            ),
        )
    }


def provider_spec(provider: LLMProvider, env: Settings) -> ProviderSpec:
    return _specs(env)[provider]


def all_specs(env: Settings) -> list[ProviderSpec]:
    return list(_specs(env).values())


def env_credentials(provider: LLMProvider, env: Settings) -> tuple[str | None, SecretStr | None]:
    """The provider's base URL and key from ``.env``, before anything saved on the screen."""
    spec = provider_spec(provider, env)
    if provider is LLMProvider.OPENROUTER:
        # LLM_BASE_URL is how OpenRouter-only installs pointed elsewhere before ADR-068.
        return env.llm_base_url or spec.base_url, env.llm_api_key
    keys: dict[LLMProvider, tuple[str | None, SecretStr | None]] = {
        LLMProvider.AZURE: (env.azure_base_url, env.azure_api_key),
        LLMProvider.OPENAI: (spec.base_url, env.openai_api_key),
        LLMProvider.ANTHROPIC: (spec.base_url, env.anthropic_api_key),
        LLMProvider.XAI: (spec.base_url, env.xai_api_key),
        LLMProvider.DEEPSEEK: (spec.base_url, env.deepseek_api_key),
        LLMProvider.CUSTOM: (env.custom_base_url, env.custom_api_key),
    }
    return keys[provider]
