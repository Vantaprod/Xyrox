"""
Xyrox — Reasoning Tool Tests (Phase 5.5)

Verifies think/plan/reflect tools are registered, validate input
strictly, and record their trace for auditing.
"""

import pytest
from app.backend.tools import build_default_registry
from app.backend.tools.base import ToolValidationError
from app.backend.tools.reasoning import (
    get_reasoning_trace,
    clear_reasoning_trace,
)


@pytest.fixture(autouse=True)
def fresh_trace():
    clear_reasoning_trace()
    yield
    clear_reasoning_trace()


# ============================================================
# REGISTRATION
# ============================================================
def test_reasoning_tools_registered():
    r = build_default_registry()
    assert "think" in r
    assert "plan" in r
    assert "reflect" in r


def test_reasoning_tools_in_schema():
    r = build_default_registry()
    names = {t["function"]["name"] for t in r.to_ai_schema()}
    assert {"think", "plan", "reflect"} <= names


# ============================================================
# think
# ============================================================
def test_think_records_thought():
    r = build_default_registry()
    result = r.execute("think", {"thought": "I need to check the DB first."})
    assert result["ok"] is True
    assert result["recorded"] == 1
    trace = get_reasoning_trace()
    assert len(trace["think"]) == 1
    assert "DB" in trace["think"][0]["thought"]


def test_think_multiple_calls():
    r = build_default_registry()
    r.execute("think", {"thought": "First"})
    r.execute("think", {"thought": "Second"})
    assert len(get_reasoning_trace()["think"]) == 2


def test_think_rejects_empty():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("think", {"thought": ""})


def test_think_rejects_whitespace():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("think", {"thought": "   "})


def test_think_rejects_too_long():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("think", {"thought": "x" * 4001})


def test_think_rejects_extra_args():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("think", {"thought": "hi", "extra": True})


# ============================================================
# plan
# ============================================================
def test_plan_records_steps():
    r = build_default_registry()
    result = r.execute("plan", {
        "goal": "Draft weekly report",
        "steps": [
            "Get work logs",
            "Calculate totals",
            "Write summary",
        ],
    })
    assert result["ok"] is True
    assert result["step_count"] == 3
    trace = get_reasoning_trace()
    assert len(trace["plan"]) == 1
    assert trace["plan"][0]["goal"] == "Draft weekly report"
    assert len(trace["plan"][0]["steps"]) == 3


def test_plan_rejects_empty_goal():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("plan", {"goal": "", "steps": ["a"]})


def test_plan_rejects_empty_steps():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("plan", {"goal": "X", "steps": []})


def test_plan_rejects_bad_step():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("plan", {"goal": "X", "steps": ["ok", ""]})


def test_plan_rejects_too_many_steps():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("plan", {
            "goal": "X",
            "steps": [f"step {i}" for i in range(51)],
        })


# ============================================================
# reflect
# ============================================================
def test_reflect_records_draft():
    r = build_default_registry()
    result = r.execute("reflect", {
        "draft": "I edited 3 videos.",
        "notes": "Missing customer name.",
    })
    assert result["ok"] is True
    trace = get_reasoning_trace()
    assert len(trace["reflect"]) == 1
    assert "3 videos" in trace["reflect"][0]["draft"]
    assert "customer" in trace["reflect"][0]["notes"]


def test_reflect_without_notes():
    r = build_default_registry()
    result = r.execute("reflect", {"draft": "Some answer"})
    assert result["ok"] is True
    assert trace_notes_empty()


def trace_notes_empty() -> bool:
    return get_reasoning_trace()["reflect"][0]["notes"] == ""


def test_reflect_rejects_empty_draft():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("reflect", {"draft": ""})


def test_reflect_rejects_non_string_notes():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("reflect", {"draft": "x", "notes": 42})


# ============================================================
# TRACE MANAGEMENT
# ============================================================
def test_clear_trace_empties_everything():
    r = build_default_registry()
    r.execute("think", {"thought": "a"})
    r.execute("plan", {"goal": "g", "steps": ["s"]})
    r.execute("reflect", {"draft": "d"})
    clear_reasoning_trace()
    trace = get_reasoning_trace()
    assert trace["think"] == []
    assert trace["plan"] == []
    assert trace["reflect"] == []


def test_trace_is_isolated_copy():
    """Modifying the returned trace must not affect the internal store."""
    r = build_default_registry()
    r.execute("think", {"thought": "original"})
    t = get_reasoning_trace()
    t["think"].append({"fake": True})
    t2 = get_reasoning_trace()
    assert len(t2["think"]) == 1