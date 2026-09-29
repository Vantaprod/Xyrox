"""
Xyrox — Reasoning Tools (Phase 5.5)

Three tools that give the AI explicit thinking stages:

    think(thought)         — record reasoning, no side effect
    plan(goal, steps)      — record an ordered plan
    reflect(draft, notes)  — record self-critique of a draft

These tools do NOT make the model smarter. They force it to
**use** its reasoning budget instead of rushing to an answer —
the same idea as extended thinking, implemented on any model.

The agent loop tracks all thoughts/plans/reflections per turn so
that:
  - The AI sees its own reasoning in context.
  - The audit log records what the AI was thinking.
  - The final answer must be justified by the thoughts.
"""

from datetime import datetime, timezone
from typing import Optional

from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


# In-process store, keyed by (agent_id, kind). The agent clears this
# at the start of each turn so the tools always reflect the CURRENT
# turn, not history. This is intentionally simple; if we need
# persistence later, it moves to the DB.
_reasoning_trace: dict[str, list[dict]] = {
    "think": [],
    "plan": [],
    "reflect": [],
}


# ============================================================
# TRACE HELPERS (used by tests and future UI)
# ============================================================
def get_reasoning_trace() -> dict:
    """Return a copy of everything recorded this session."""
    return {k: list(v) for k, v in _reasoning_trace.items()}


def clear_reasoning_trace() -> None:
    """Clear all recorded reasoning. Called at the start of each turn."""
    for k in _reasoning_trace:
        _reasoning_trace[k].clear()


# ============================================================
# TOOL: think
# ============================================================
def think(thought: str, **extra) -> dict:
    """
    Record a reasoning step. Returns an acknowledgment so the model
    sees its thought was stored.
    """
    if extra:
        raise ToolValidationError(
            f"think got unexpected args: {sorted(extra)}"
        )
    if not isinstance(thought, str) or not thought.strip():
        raise ToolValidationError("thought must be a non-empty string.")
    text = thought.strip()
    if len(text) > 4000:
        raise ToolValidationError("thought must be <= 4000 characters.")

    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "thought": text,
    }
    _reasoning_trace["think"].append(entry)
    return {"ok": True, "recorded": len(_reasoning_trace["think"])}


# ============================================================
# TOOL: plan
# ============================================================
def plan(goal: str, steps: list, **extra) -> dict:
    """
    Record a plan: a goal and an ordered list of steps.
    """
    if extra:
        raise ToolValidationError(
            f"plan got unexpected args: {sorted(extra)}"
        )
    if not isinstance(goal, str) or not goal.strip():
        raise ToolValidationError("goal must be a non-empty string.")
    if not isinstance(steps, list) or not steps:
        raise ToolValidationError("steps must be a non-empty list.")
    clean_steps: list[str] = []
    for s in steps:
        if not isinstance(s, str) or not s.strip():
            raise ToolValidationError(
                "every step must be a non-empty string."
            )
        clean_steps.append(s.strip())
    if len(clean_steps) > 50:
        raise ToolValidationError("plan must have <= 50 steps.")

    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "goal": goal.strip(),
        "steps": clean_steps,
    }
    _reasoning_trace["plan"].append(entry)
    return {
        "ok": True,
        "goal": entry["goal"],
        "step_count": len(clean_steps),
        "recorded": len(_reasoning_trace["plan"]),
    }


# ============================================================
# TOOL: reflect
# ============================================================
def reflect(draft: str, notes: Optional[str] = None, **extra) -> dict:
    """
    Record a self-critique of a draft answer.
    """
    if extra:
        raise ToolValidationError(
            f"reflect got unexpected args: {sorted(extra)}"
        )
    if not isinstance(draft, str) or not draft.strip():
        raise ToolValidationError("draft must be a non-empty string.")
    if notes is not None and not isinstance(notes, str):
        raise ToolValidationError("notes must be a string or None.")

    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "draft": draft.strip(),
        "notes": (notes or "").strip(),
    }
    _reasoning_trace["reflect"].append(entry)
    return {"ok": True, "recorded": len(_reasoning_trace["reflect"])}


# ============================================================
# REGISTRATION
# ============================================================
def register_reasoning_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="think",
        description=(
            "Record a reasoning step. Use BEFORE acting on a complex "
            "request: write what you understand, what is uncertain, "
            "and what you plan to do. This is not visible to the user; "
            "it is your scratchpad. Calling think() first improves "
            "the quality of your final answer. You may call it "
            "multiple times."
        ),
        parameters={
            "type": "object",
            "properties": {
                "thought": {
                    "type": "string",
                    "description": (
                        "Your reasoning. Up to 4000 characters. "
                        "Be specific: what do you know, what do you "
                        "need, what is your next step."
                    ),
                },
            },
            "required": ["thought"],
        },
        func=think,
    ))

    registry.register(Tool(
        name="plan",
        description=(
            "Record an ordered plan for a multi-step task. Use when "
            "the request has multiple steps (e.g. 'generate my "
            "weekly report and export as PDF'). Include a short goal "
            "and 2-50 ordered steps. Do NOT execute steps here — "
            "just record them. Then execute them one by one."
        ),
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of short step descriptions.",
                },
            },
            "required": ["goal", "steps"],
        },
        func=plan,
    ))

    registry.register(Tool(
        name="reflect",
        description=(
            "Critique your own draft answer before sending it. Use "
            "AFTER you have a draft but BEFORE your final response. "
            "In the notes, list what is missing, what is uncertain, "
            "and what would make the answer stronger. Then revise."
        ),
        parameters={
            "type": "object",
            "properties": {
                "draft": {
                    "type": "string",
                    "description": "Your current draft answer.",
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Self-critique: gaps, uncertainty, improvements."
                    ),
                },
            },
            "required": ["draft"],
        },
        func=reflect,
    ))