"""
Xyrox — AI Provider Abstraction (Phase 2, File 1)

This is the model-agnostic interface every AI provider must implement.
It separates MODEL from AGENT from TOOLS from DATABASE (Master Command §4).

The application code never calls Ollama, OpenAI, Anthropic, or Gemini
directly. It always calls through this interface. Swapping providers is
a configuration change (AI_PROVIDER in .env), never a code rewrite.

Design rules:
- No provider-specific logic leaks into this file.
- All methods raise AIProviderError on failure (defined below).
- No fabrication: if the model returns nonsense, we raise, never invent.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ============================================================
# ERROR TYPE
# ============================================================
class AIProviderError(Exception):
    """Raised when an AI provider fails. Never swallowed silently."""
    pass


# ============================================================
# RESULT TYPES
# ============================================================
@dataclass
class AIResponse:
    """
    Standard response returned by any AI provider.

    content:      The text response from the model.
    model:        The exact model name used (e.g. "llama3.2:3b").
    provider:     The provider that answered (e.g. "ollama").
    raw:          The raw provider response, for debugging/logging.
    tool_calls:   Structured tool calls, if the model returned any.
                  Each entry is a dict with keys:
                      name       — the tool name
                      arguments  — dict of arguments
    """
    content: str
    model: str
    provider: str
    raw: dict = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)


# ============================================================
# ABSTRACT PROVIDER
# ============================================================
class AIProvider(ABC):
    """
    Base class for all AI providers.

    Every concrete provider (Ollama, OpenAI, Anthropic, Gemini, ...)
    must implement these methods. Nothing else.
    """

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if the provider can be reached and is ready.
        Must NOT raise. Returns False on any error.
        """
        ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """
        Send a chat-style conversation to the model.

        messages : list of {"role": "system"|"user"|"assistant", "content": str}
        model    : override the default model (optional)
        tools    : optional tool schema definitions (OpenAI-format)
        temperature : sampling temperature (0.0 = deterministic)
        max_tokens  : optional cap on response length

        Returns AIResponse. Raises AIProviderError on failure.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """
        Return the list of model names available on this provider.
        Must NOT raise. Returns empty list on error.
        """
        ...