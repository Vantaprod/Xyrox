"""
Xyrox — Excel Tools (Phase 5.4)

Exposes the Excel engine as tools the AI can call:

    inspect_excel(path)                          → structural dump
    map_excel_template(path, sheet_name=None)    → section/field map
    fill_excel_template(source_path, cell_values, ...) → filled copy

Design rules:
- All file paths are validated. Missing files raise ToolValidationError.
- Inspection and mapping are read-only — never touch the source.
- Filling always copies. Original is never modified.
- Outputs are JSON-serializable so the AI can reason about them.
- Errors bubble up clearly; nothing is hidden.
"""

from typing import Any, Optional

from app.backend.excel.inspector import (
    inspect_workbook,
    workbook_info_to_dict,
    ExcelInspectionError,
)
from app.backend.excel.template_mapper import (
    map_template,
    template_map_to_dict,
    TemplateMappingError,
)
from app.backend.excel.filler import (
    fill_template,
    fill_result_to_dict,
    ExcelFillError,
)
from app.backend.tools.base import Tool, ToolValidationError
from app.backend.tools.registry import ToolRegistry


# ============================================================
# TOOL FUNCTIONS
# ============================================================
def inspect_excel(path: str, include_cells: bool = True) -> dict:
    """
    Inspect an Excel workbook and return its structure as JSON.
    Never writes to the file.
    """
    if not isinstance(path, str) or not path.strip():
        raise ToolValidationError("path must be a non-empty string.")
    if not isinstance(include_cells, bool):
        raise ToolValidationError("include_cells must be a boolean.")

    try:
        info = inspect_workbook(path.strip(), include_cells=include_cells)
    except ExcelInspectionError as exc:
        raise ToolValidationError(str(exc)) from exc

    return workbook_info_to_dict(info)


def map_excel_template(path: str, sheet_name: Optional[str] = None) -> dict:
    """
    Build a section/field map for an Excel template.
    Never writes to the file.
    """
    if not isinstance(path, str) or not path.strip():
        raise ToolValidationError("path must be a non-empty string.")
    if sheet_name is not None and not isinstance(sheet_name, str):
        raise ToolValidationError("sheet_name must be a string or None.")

    try:
        info = inspect_workbook(path.strip())
        tm = map_template(info, sheet_name)
    except ExcelInspectionError as exc:
        raise ToolValidationError(str(exc)) from exc
    except TemplateMappingError as exc:
        raise ToolValidationError(str(exc)) from exc

    return template_map_to_dict(tm)


def fill_excel_template(
    source_path: str,
    cell_values: dict,
    sheet_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    allow_formula_overwrite: bool = False,
) -> dict:
    """
    Write values into a COPY of an Excel template and verify the output.
    The original file is never modified.

    cell_values: {"A1": 5, "B2": "text", ...}
    Returns a FillResult dict with per-cell verification.
    """
    if not isinstance(source_path, str) or not source_path.strip():
        raise ToolValidationError("source_path must be a non-empty string.")
    if not isinstance(cell_values, dict) or not cell_values:
        raise ToolValidationError("cell_values must be a non-empty dict.")
    if sheet_name is not None and not isinstance(sheet_name, str):
        raise ToolValidationError("sheet_name must be a string or None.")
    if output_dir is not None and not isinstance(output_dir, str):
        raise ToolValidationError("output_dir must be a string or None.")
    if not isinstance(allow_formula_overwrite, bool):
        raise ToolValidationError("allow_formula_overwrite must be a boolean.")

    try:
        result = fill_template(
            source_path=source_path.strip(),
            cell_values=cell_values,
            sheet_name=sheet_name,
            output_dir=output_dir,
            allow_formula_overwrite=allow_formula_overwrite,
        )
    except ExcelFillError as exc:
        raise ToolValidationError(str(exc)) from exc

    return fill_result_to_dict(result)


# ============================================================
# REGISTRATION
# ============================================================
def register_excel_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="inspect_excel",
        description=(
            "Read the structure of an Excel workbook: sheets, cells, "
            "formulas, merged ranges, formatting, hidden rows/columns. "
            "Returns a JSON description. Never modifies the file. "
            "Use this BEFORE deciding how to fill a template."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the .xlsx or .xlsm file.",
                },
                "include_cells": {
                    "type": "boolean",
                    "description": (
                        "If false, only sheet metadata is returned "
                        "(faster for large workbooks). Default: true."
                    ),
                },
            },
            "required": ["path"],
        },
        func=inspect_excel,
    ))

    registry.register(Tool(
        name="map_excel_template",
        description=(
            "Build an adaptive map of an Excel report template: "
            "sections, field labels, input cells, inferred types "
            "(integer, currency, date, percent, text). "
            "Never modifies the file. Use this to understand WHERE "
            "values should go in a template before filling it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "sheet_name": {
                    "type": "string",
                    "description": "Optional sheet name. Defaults to active.",
                },
            },
            "required": ["path"],
        },
        func=map_excel_template,
    ))

    registry.register(Tool(
        name="fill_excel_template",
        description=(
            "Fill an Excel template by writing values into a COPY. "
            "The original file is NEVER modified. Every write is "
            "verified by re-opening the output. "
            "Refuses to overwrite formula cells unless explicitly "
            "allowed. Returns the output file path and per-cell "
            "verification. Use after map_excel_template to know "
            "which cells to write."
        ),
        parameters={
            "type": "object",
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "Path to the original template.",
                },
                "cell_values": {
                    "type": "object",
                    "description": (
                        "Mapping of cell coordinate → value. "
                        "Example: {\"B3\": 5, \"B4\": 12.5, \"B5\": \"Done\"}."
                    ),
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Optional sheet name.",
                },
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Directory for the filled copy. "
                        "Defaults to the source directory."
                    ),
                },
                "allow_formula_overwrite": {
                    "type": "boolean",
                    "description": (
                        "Default false. If true, allows overwriting "
                        "formula cells. Use with caution."
                    ),
                },
            },
            "required": ["source_path", "cell_values"],
        },
        func=fill_excel_template,
    ))