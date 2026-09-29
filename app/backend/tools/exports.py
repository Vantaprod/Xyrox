"""
Xyrox — Export Tools (Phase 4.4)

Tools the AI can call to export a report to a file:
    export_report(report_id, format)
    export_report_text(report_id, format)   # returns file path only
"""

from app.backend.services.report_builder import get_report
from app.backend.exports.exporters import export_report as _export_report
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


def _require_report(report_id: int) -> dict:
    if not isinstance(report_id, int) or report_id < 1:
        raise ToolValidationError("report_id must be a positive integer.")
    report = get_report(report_id)
    if report is None:
        raise ToolValidationError(f"Report id={report_id} not found.")
    return report


def export_report_to_file(
    report_id: int,
    format: str = "pdf",
    **extra,
) -> dict:
    if extra:
        raise ToolValidationError(
            f"export_report got unexpected args: {sorted(extra)}"
        )
    report = _require_report(report_id)
    try:
        path = _export_report(report, format)
    except Exception as exc:
        raise ToolValidationError(f"Export failed: {exc}") from exc
    return {
        "report_id": report_id,
        "format": format,
        "file_path": path,
        "report_type": report.get("report_type"),
        "period_start": report.get("period_start"),
        "period_end": report.get("period_end"),
    }


def register_export_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="export_report",
        description=(
            "Export a previously generated report to a file. Supports "
            "formats: pdf, docx, html, md, txt. Returns the absolute file "
            "path. Use after create_daily_report / create_weekly_report / "
            "create_monthly_report, when the user asks for a file to be "
            "generated."
        ),
        parameters={
            "type": "object",
            "properties": {
                "report_id": {
                    "type": "integer",
                    "description": "The id returned by create_*_report.",
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx", "html", "md", "txt"],
                    "description": "Output format. Default: pdf.",
                },
            },
            "required": ["report_id"],
        },
        func=export_report_to_file,
    ))