"""
Xyrox — AI Provider Factory (Phase 2, File 3, fixed)

Central place where the correct AI provider is chosen based on
configuration (Master Command §4, §38).

The rest of the application never imports OllamaProvider directly.
It calls get_provider() and receives an AIProvider interface.

Master Command §38 declares the canonical env value is
    AI_PROVIDER=local
for local inference, with openai / anthropic / gemini as future
cloud options. We therefore register "local" as the canonical
name, and keep "ollama" as an explicit alias for clarity.

Adding a new provider later:
1. Create app/backend/ai/openai_provider.py
2. Add one line to _PROVIDER_REGISTRY below.
3. Set AI_PROVIDER=openai in .env.
No other code changes required.
"""

from typing import Optional

from app.backend.ai.base import AIProvider, AIProviderError
from app.backend.ai.ollama_provider import OllamaProvider
from app.backend.config import settings


# ============================================================
# PROVIDER REGISTRY
# ============================================================
# Only providers that actually exist are listed here.
# Attempting to use an unlisted provider raises AIProviderError.
# This prevents the "fake AI button" anti-pattern (Master Command §50).
#
# "local" and "ollama" both map to the same local implementation —
# "local" is the canonical name per Master Command §38.
# ============================================================
_PROVIDER_REGISTRY = {
    "local": OllamaProvider,
    "ollama": OllamaProvider,
    # "openai":    OpenAIProvider,     # not implemented yet
    # "anthropic": AnthropicProvider,  # not implemented yet
    # "gemini":    GeminiProvider,     # not implemented yet
}


# Cache so we do not create a new client on every request
_cached_provider: Optional[AIProvider] = None
_cached_name: Optional[str] = None


def get_provider(force_new: bool = False) -> AIProvider:
    """
    Return the configured AI provider instance.

    The provider name comes from settings.AI_PROVIDER (set in .env).
    Default is "local", which maps to OllamaProvider.

    Raises AIProviderError if the configured provider is not implemented.
    """
    global _cached_provider, _cached_name

    provider_name = (settings.AI_PROVIDER or "local").strip().lower()

    # Return cached instance if it matches the current config
    if (
        not force_new
        and _cached_provider is not None
        and _cached_name == provider_name
    ):
        return _cached_provider

    if provider_name not in _PROVIDER_REGISTRY:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise AIProviderError(
            f"AI_PROVIDER='{provider_name}' is not implemented. "
            f"Currently available: {available}."
        )

    provider_class = _PROVIDER_REGISTRY[provider_name]
    _cached_provider = provider_class()
    _cached_name = provider_name
    return _cached_provider


def reset_provider_cache() -> None:
    """
    Clear the cached provider. Used by tests to force a fresh instance.
    """
    global _cached_provider, _cached_name
    _cached_provider = None
    _cached_name = None


def list_available_providers() -> list[str]:
    """
    Return the list of provider names that have real implementations.
    Used by the dashboard and by the /health endpoint.
    """
    return sorted(_PROVIDER_REGISTRY.keys())