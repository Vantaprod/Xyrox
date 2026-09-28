"""
Xyrox — Ollama Provider (Phase 2, File 2)

Concrete implementation of AIProvider that talks to a local Ollama server.

This provider assumes:
- Ollama is installed and running (verified in Phase 2 sub-phase 0).
- The default model is set in .env as AI_MODEL.
- The Ollama HTTP endpoint is OLLAMA_BASE_URL (default http://localhost:11434).

Design rules:
- No fabrication: if Ollama fails, raise AIProviderError.
- No silent success: every failure path is explicit.
- No model name hardcoding: model comes from config or caller.
- Tool calls are returned structurally, not executed here.
"""

from typing import Optional

import ollama as ollama_client

from app.backend.ai.base import AIProvider, AIResponse, AIProviderError
from app.backend.config import settings


class OllamaProvider(AIProvider):
    """
    AI provider backed by a local Ollama server.

    Instantiate with no arguments to use defaults from .env:
        provider = OllamaProvider()

    Or override:
        provider = OllamaProvider(
            model="llama3.1:8b-instruct-q4_K_M",
            base_url="http://localhost:11434",
        )
    """

    name = "ollama"

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model or settings.AI_MODEL
        self.base_url = base_url or settings.OLLAMA_BASE_URL

        # The ollama Python client is instantiated per call with the
        # correct host, so multiple providers can coexist if needed.
        self._client = ollama_client.Client(host=self.base_url)

    # ------------------------------------------------------------
    # AVAILABILITY
    # ------------------------------------------------------------
    def is_available(self) -> bool:
        """
        Return True if Ollama is running and reachable.
        Never raises.
        """
        try:
            self._client.list()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------
    # MODEL LISTING
    # ------------------------------------------------------------
    def list_models(self) -> list[str]:
        """
        Return all model tags installed in Ollama.
        Never raises. Returns [] on failure.
        """
        try:
            response = self._client.list()
            # ollama client returns an object with .models (list of dicts)
            models = getattr(response, "models", None) or []
            names: list[str] = []
            for m in models:
                # each entry is dict-like with 'model' or 'name' key
                if isinstance(m, dict):
                    name = m.get("model") or m.get("name")
                else:
                    name = getattr(m, "model", None) or getattr(m, "name", None)
                if name:
                    names.append(name)
            return names
        except Exception:
            return []

    # ------------------------------------------------------------
    # CHAT
    # ------------------------------------------------------------
    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> AIResponse:
        """
        Send a chat conversation to Ollama and return a normalized AIResponse.

        messages : [{"role": "system"|"user"|"assistant", "content": "..."}]
        model    : override the default model for this call
        tools    : optional tool schema (OpenAI-style). Passed through to
                   Ollama, which supports tool calling on compatible models.
        temperature : sampling temperature
        max_tokens  : optional response length cap

        Raises AIProviderError on any failure.
        """
        if not messages:
            raise AIProviderError("chat() called with empty messages list.")

        chosen_model = model or self.model

        # Build the kwargs for the Ollama client.
        # Ollama's Python client uses "options" for generation parameters.
        options: dict = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        kwargs: dict = {
            "model": chosen_model,
            "messages": messages,
            "options": options,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            raw = self._client.chat(**kwargs)
        except Exception as exc:
            raise AIProviderError(
                f"Ollama chat failed (model={chosen_model}, "
                f"url={self.base_url}): {exc}"
            ) from exc

        return self._normalize(raw, chosen_model)

    # ------------------------------------------------------------
    # INTERNAL — normalize Ollama's response to our AIResponse
    # ------------------------------------------------------------
    def _normalize(self, raw, model_name: str) -> AIResponse:
        """
        Convert the ollama client's response object into our AIResponse.
        Extracts content and any tool calls.
        """
        # The ollama client returns a ChatResponse-like object.
        # It is usually dict-accessible; we defensively handle both styles.
        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        message = _get(raw, "message", {}) or {}
        content = _get(message, "content", "") or ""

        # Tool calls
        tool_calls_raw = _get(message, "tool_calls", None) or []
        tool_calls: list[dict] = []
        for tc in tool_calls_raw:
            # ollama returns {"function": {"name": ..., "arguments": {...}}}
            fn = _get(tc, "function", {}) or {}
            tool_calls.append(
                {
                    "name": _get(fn, "name", "") or "",
                    "arguments": _get(fn, "arguments", {}) or {},
                }
            )

        # Convert raw object to a plain dict for logging if possible
        raw_dict: dict = {}
        if isinstance(raw, dict):
            raw_dict = raw
        else:
            try:
                raw_dict = dict(raw)  # type: ignore[arg-type]
            except Exception:
                raw_dict = {"_repr": repr(raw)}

        return AIResponse(
            content=content,
            model=model_name,
            provider=self.name,
            raw=raw_dict,
            tool_calls=tool_calls,
        )