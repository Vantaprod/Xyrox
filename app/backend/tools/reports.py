"""
Xyrox — Report Tools (Phase 4.3)

Tools the AI can call to generate report drafts:
    create_daily_report()
    create_weekly_report()
    create_monthly_report()

Each tool:
  1. Pulls verified numbers from the calculation layer.
  2. Pulls raw work logs and tasks from the database.
  3. Stores a draft in the reports table.
  4. Returns the structured draft to the AI.

The AI is expected to write the report prose in professional English
using ONLY the numbers in the returned draft. It cannot invent values.

Master Command §18, §19, §20, §21, §22, §24, §48.
"""

from typing import Optional

from app.backend.services.report_builder import (
    build_daily_report,
    build_weekly_report,
    build_monthly_report,
    get_report,
)
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


# ============================================================
# TOOL FUNCTIONS
# ============================================================
def create_daily_report(day: Optional[str] = None, **extra) -> dict:
    if extra:
        raise ToolValidationError(
            f"create_daily_report got unexpected args: {sorted(extra)}"
        )
    return build_daily_report(day)


def create_weekly_report(week_start: Optional[str] = None, **extra) -> dict:
    if extra:
        raise ToolValidationError(
            f"create_weekly_report got unexpected args: {sorted(extra)}"
        )
    return build_weekly_report(week_start)


def create_monthly_report(
    year: Optional[int] = None,
    month: Optional[int] = None,
    **extra,
) -> dict:
    if extra:
        raise ToolValidationError(
            f"create_monthly_report got unexpected args: {sorted(extra)}"
        )
    return build_monthly_report(year, month)


def get_report_by_id(report_id: int, **extra) -> dict:
    if extra:
        raise ToolValidationError(
            f"get_report_by_id got unexpected args: {sorted(extra)}"
        )
    if not isinstance(report_id, int) or report_id < 1:
        raise ToolValidationError("report_id must be a positive integer.")
    result = get_report(report_id)
    if result is None:
        raise ToolValidationError(f"Report id={report_id} not found.")
    return result


# ============================================================
# REGISTRATION
# ============================================================
def register_report_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="create_daily_report",
        description=(
            "Create a DAILY report draft from verified data. Returns a "
            "structured draft with verified_numbers, raw work logs, and "
            "outstanding tasks. After calling this tool, write the report "
            "in professional English using ONLY the numbers in "
            "verified_numbers. Do not invent numbers. For any section "
            "listed in missing_sections, write 'NOT PROVIDED' — never guess."
        ),
        parameters={
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": (
                        "Optional ISO 8601 date (YYYY-MM-DD). "
                        "Defaults to today."
                    ),
                },
            },
            "required": [],
        },
        func=create_daily_report,
    ))

    registry.register(Tool(
        name="create_weekly_report",
        description=(
            "Create a WEEKLY report draft (Monday-to-Monday). Same rules "
            "as create_daily_report: use verified_numbers exactly, never "
            "invent, write 'NOT PROVIDED' for empty sections."
        ),
        parameters={
            "type": "object",
            "properties": {
                "week_start": {
                    "type": "string",
                    "description": (
                        "Optional ISO 8601 date of the Monday to report on. "
                        "Defaults to this week's Monday."
                    ),
                },
            },
            "required": [],
        },
        func=create_weekly_report,
    ))

    registry.register(Tool(
        name="create_monthly_report",
        description=(
            "Create a MONTHLY report draft for a calendar month. Same rules "
            "as the other report tools."
        ),
        parameters={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "e.g. 2026"},
                "month": {"type": "integer", "description": "1-12"},
            },
            "required": [],
        },
        func=create_monthly_report,
    ))

    registry.register(Tool(
        name="get_report",
        description=(
            "Fetch a previously generated report by id. Use when the user "
            "wants to see a report that already exists."
        ),
        parameters={
            "type": "object",
            "properties": {
                "report_id": {"type": "integer"},
            },
            "required": ["report_id"],
        },
        func=get_report_by_id,
    ))