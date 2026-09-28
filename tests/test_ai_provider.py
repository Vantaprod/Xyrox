"""
Xyrox — AI Provider Tests (Phase 2, File 4)

These tests hit the REAL Ollama server. They are not mocks.
If Ollama is not running or the model is not installed, the tests
SKIP (they do not fail) — because a missing AI runtime is an
environmental issue, not a code bug.

To run only these tests:
    python -m pytest tests/test_ai_provider.py -v

The test suite proves:
- The factory returns the configured provider.
- The factory rejects unimplemented providers explicitly.
- OllamaProvider.is_available() tells the truth.
- OllamaProvider.list_models() sees llama3.2:3b.
- OllamaProvider.chat() returns a coherent, non-empty response.
- AIResponse has the correct structure.
"""

import pytest

from app.backend.ai.base import AIProvider, AIResponse, AIProviderError
from app.backend.ai.factory import (
    get_provider,
    reset_provider_cache,
    list_available_providers,
)
from app.backend.config import settings


# ============================================================
# FIXTURES
# ============================================================
@pytest.fixture(scope="module")
def provider() -> AIProvider:
    """Return the configured provider. Skips if unavailable."""
    reset_provider_cache()
    p = get_provider()
    if not p.is_available():
        pytest.skip(
            f"AI provider '{p.name}' is not available. "
            f"Start Ollama with 'ollama serve' and re-run."
        )
    return p


# ============================================================
# FACTORY TESTS
# ============================================================
def test_factory_returns_configured_provider():
    """The factory must return a working provider for the configured name."""
    reset_provider_cache()
    p = get_provider()
    # Both "local" and "ollama" map to OllamaProvider. The canonical
    # class name is "ollama". So assert on that.
    assert p.name == "ollama"


def test_factory_caches_provider():
    """Two calls to get_provider() return the same instance."""
    reset_provider_cache()
    p1 = get_provider()
    p2 = get_provider()
    assert p1 is p2


def test_factory_force_new():
    """force_new=True returns a fresh instance."""
    p1 = get_provider()
    p2 = get_provider(force_new=True)
    assert p1 is not p2


def test_factory_rejects_unimplemented_provider(monkeypatch):
    """
    Setting AI_PROVIDER to something not implemented must raise
    AIProviderError — never silently fall back (Master Command §50).
    """
    reset_provider_cache()
    monkeypatch.setattr(settings, "AI_PROVIDER", "fake_provider_xyz")
    with pytest.raises(AIProviderError) as exc:
        get_provider()
    assert "fake_provider_xyz" in str(exc.value)
    reset_provider_cache()


def test_list_available_providers_contains_ollama():
    """The registry must include the Ollama provider."""
    providers = list_available_providers()
    assert "ollama" in providers


# ============================================================
# PROVIDER TESTS (REAL OLLAMA)
# ============================================================
def test_provider_is_available(provider: AIProvider):
    """If we got this far, is_available() must be True."""
    assert provider.is_available() is True


def test_provider_lists_models(provider: AIProvider):
    """The installed models list must contain llama3.2:3b."""
    models = provider.list_models()
    assert isinstance(models, list)
    assert any("llama3.2:3b" in m for m in models), (
        f"llama3.2:3b not found in {models}. "
        f"Run: ollama pull llama3.2:3b"
    )


def test_provider_chat_returns_response(provider: AIProvider):
    """
    Send a simple prompt and verify we get a coherent AIResponse.
    This is the moment we prove Xyrox can talk to a real local LLM.
    """
    response = provider.chat(
        messages=[
            {"role": "system", "content": "You are a factual assistant. Answer with one short sentence."},
            {"role": "user", "content": "Reply with exactly: Xyrox is online."},
        ],
        temperature=0.0,
    )

    # Structure assertions
    assert isinstance(response, AIResponse)
    assert response.provider == "ollama"
    assert response.model  # non-empty
    assert isinstance(response.content, str)
    assert len(response.content.strip()) > 0
    assert isinstance(response.raw, dict)
    assert isinstance(response.tool_calls, list)

    # Content assertion — the model should say something including "Xyrox"
    # (we do not require exact match, because CPU inference sometimes
    # varies punctuation and capitalization).
    assert "xyrox" in response.content.lower(), (
        f"Unexpected response: {response.content!r}"
    )


def test_provider_chat_rejects_empty_messages(provider: AIProvider):
    """An empty messages list must raise AIProviderError, not crash."""
    with pytest.raises(AIProviderError):
        provider.chat(messages=[])


def test_provider_chat_custom_model(provider: AIProvider):
    """
    Passing an explicit model name must use that model.
    We use the same one we know is installed.
    """
    response = provider.chat(
        messages=[{"role": "user", "content": "Say hi."}],
        model="llama3.2:3b",
        temperature=0.0,
    )
    assert response.model == "llama3.2:3b"


def test_provider_chat_nonexistent_model_raises(provider: AIProvider):
    """
    Asking for a model that does not exist must raise AIProviderError.
    No fabrication, no silent fallback (Master Command §18).
    """
    with pytest.raises(AIProviderError):
        provider.chat(
            messages=[{"role": "user", "content": "Hi."}],
            model="definitely-not-a-real-model-xyz:999b",
            temperature=0.0,
        )