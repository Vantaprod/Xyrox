"""
Xyrox — Chat Schemas (Phase 3, File 7)

Pydantic models for the /api/v1/chat endpoint.

Rules:
- Message content is bounded to a sane length.
- The response exposes the AI's text, tool calls, and audit metadata.
- No internal state (conversation history, prompts) is exposed.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)


class ToolCallInfo(BaseModel):
    """A record of one tool call the agent executed."""
    model_config = ConfigDict(from_attributes=True)
    name: str
    arguments: dict
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None


class ChatResponse(BaseModel):
    """The result of one user message."""
    message: str
    tool_calls: list[ToolCallInfo] = Field(default_factory=list)
    iterations: int
    model: str
    provider: str
    timestamp: datetime


class ChatResetResponse(BaseModel):
    """Result of clearing the user's conversation."""
    cleared: bool
    message: str