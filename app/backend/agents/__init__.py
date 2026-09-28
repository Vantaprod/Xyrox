"""
Xyrox — Agents Package

The agent is the loop that connects the AI provider, the tool registry,
and the conversation. It is the only place where the model's tool
requests are executed against real systems.
"""

from app.backend.agents.agent import Agent, AgentResult
from app.backend.agents.prompts import build_system_prompt

__all__ = ["Agent", "AgentResult", "build_system_prompt"]