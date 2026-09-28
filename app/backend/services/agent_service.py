"""
Xyrox — Agent Service (Phase 3, File 8)

Holds one Agent per user, keyed by user id. Provides a thin wrapper
that the HTTP layer can call without knowing about the Agent class.

Design:
- In-memory cache. Restarting the server clears all conversations.
- Thread-safe enough for a single-user local system.
- Each user gets an independent conversation history.
- reset_agent(user_id) clears one conversation.
- reset_all() clears everything (used by tests).
"""

import threading
from typing import Optional

from app.backend.agents.agent import Agent, AgentResult
from app.backend.models.models import User


_lock = threading.Lock()
_agents: dict[int, Agent] = {}


def _build_agent_for(user: User) -> Agent:
    """
    Build a fresh Agent for a user. Uses a small amount of extra
    context so the model knows who it is talking to.
    """
    extra = f"You are speaking with {user.full_name or user.username}."
    return Agent(
        timezone=user.timezone or "Africa/Lagos",
        extra_system_context=extra,
    )


def get_agent_for(user: User) -> Agent:
    """Return the cached Agent for this user, or create one."""
    with _lock:
        agent = _agents.get(user.id)
        if agent is None:
            agent = _build_agent_for(user)
            _agents[user.id] = agent
        return agent


def chat_with_agent(user: User, message: str) -> AgentResult:
    """
    Send a message to this user's agent and return the result.
    """
    agent = get_agent_for(user)
    return agent.chat(message)


def reset_agent(user_id: int) -> bool:
    """Clear a specific user's conversation. Returns True if it existed."""
    with _lock:
        agent = _agents.get(user_id)
        if agent is None:
            return False
        agent.reset()
        return True


def reset_all() -> None:
    """Clear every cached agent. Used by tests."""
    with _lock:
        _agents.clear()