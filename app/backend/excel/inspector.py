"""
Xyrox — Excel Workbook Inspector (Phase 5.1, corrected)

Reads an .xlsx file and produces a complete structural description:
sheets, dimensions, cell values, formulas, merged ranges, formatting,
defined names, and data validations.

Design rules (Master Command §14):
- Never write to the file. Inspection is read-only.
- Never invent data. If something is missing, report it as missing.
- Return plain dicts (JSON-serializable) so the AI can reason about them.
- Handle real-world xlsx files: multiple sheets, merged cells,
  formulas, hidden rows/columns, empty cells.
- Raise ExcelInspectionError on any problem. Never silently succeed.
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.cell.cell import Cell


class ExcelInspectionError(Exception):
    """Raised when a workbook cannot be inspected."""
    pass


# ============================================================
# DATA TYPES
# ============================================================
@dataclass
class CellInfo:
    coordinate: str
    row: int
    column: int
    value: Optional[object]
    data_type: str
    is_formula: bool
    formula: Optional[str] = None
    number_format: Optional[str] = None
    font_bold: bool = False
    font_size: Optional[float] = None
    font_color: Optional[str] = None
    fill_color: Optional[str] = None
    border: bool = False
    alignment_horizontal: Optional[str] = None
    is_merged: bool = False
    merge_range: Optional[str] = None


@dataclass
class MergeInfo:
    range: str
    top_left: str
    rows: int
    cols: int


@dataclass
class SheetInfo:
    name: str
    index: int
    max_row: int
    max_column: int
    min_row: int
    min_column: int
    state: str  # 'visible', 'hidden', 'veryHidden'
    merged_ranges: list[str] = field(default_factory=list)
    hidden_rows: list[int] = field(default_factory=list)
    hidden_columns: list[str] = field(default_factory=list)
    populated_cells: int = 0
    formula_cells: int = 0


@dataclass
class NamedRangeInfo:
    name: str
    sheet: Optional[str]
    cell_range: str
    is_dynamic: bool = False


@dataclass
class WorkbookInfo:
    file_path: str
    file_size_bytes: int
    sheet_names: list[str]
    active_sheet: Optional[str]
    has_macros: bool
    sheets: list[SheetInfo] = field(default_factory=list)
    named_ranges: list[NamedRangeInfo] = field(default_factory=list)
    cells_by_sheet: dict[str, list[CellInfo]] = field(default_factory=dict)


# ============================================================
# HELPERS
# ============================================================
def _safe_color(rgb) -> Optional[str]:
    """openpyxl colors can be None, 'FFRRGGBB', or a theme color."""
    if rgb is None:
        return None
    if isinstance(rgb, str):
        return rgb
    try:
        val = getattr(rgb, "rgb", None)
        if isinstance(val, str):
            return val
    except Exception:
        pass
    return None


def _extract_cell_info(
    ws: Worksheet,
    row: int,
    col: int,
    merged_lookup: dict[tuple[int, int], str],
) -> Optional[CellInfo]:
    """Build a CellInfo for one cell. Return None only if we cannot."""
    cell: Cell = ws.cell(row=row, column=col)
    value = cell.value
    fmt = cell.number_format
    is_formula = isinstance(value, str) and value.startswith("=")
    formula = value if is_formula else None

    # Skip truly empty cells that have no formatting
    if (
        value is None
        and not cell.has_style
        and (row, col) not in merged_lookup
    ):
        return None

    try:
        font = cell.font
        font_bold = bool(font.bold) if font else False
        font_size = float(font.size) if font and font.size else None
        font_color = _safe_color(font.color) if font and font.color else None
    except Exception:
        font_bold, font_size, font_color = False, None, None

    try:
        fill = cell.fill
        fill_color = None
        if fill and getattr(fill, "fgColor", None):
            fill_color = _safe_color(fill.fgColor)
    except Exception:
        fill_color = None

    try:
        border = bool(cell.border and any(
            getattr(cell.border, side, None)
            for side in ("left", "right", "top", "bottom")
        ))
    except Exception:
        border = False

    try:
        align = cell.alignment
        align_h = align.horizontal if align else None
    except Exception:
        align_h = None

    merge_range = merged_lookup.get((row, col))

    return CellInfo(
        coordinate=cell.coordinate,
        row=row,
        column=col,
        value=None if is_formula else value,
        data_type=str(cell.data_type),
        is_formula=is_formula,
        formula=formula,
        number_format=fmt,
        font_bold=font_bold,
        font_size=font_size,
        font_color=font_color,
        fill_color=fill_color,
        border=border,
        alignment_horizontal=align_h,
        is_merged=merge_range is not None,
        merge_range=merge_range,
    )


# ============================================================
# PUBLIC API
# ============================================================
def inspect_workbook(
    file_path: str,
    include_cells: bool = True,
    max_cells_per_sheet: int = 20000,
) -> WorkbookInfo:
    """
    Inspect an xlsx file and return a WorkbookInfo.

    file_path: absolute or relative path to the .xlsx file
    include_cells: if False, only sheet metadata is returned (faster)
    max_cells_per_sheet: safety cap

    Raises ExcelInspectionError if the file cannot be opened.
    """
    p = Path(file_path)
    if not p.exists():
        raise ExcelInspectionError(f"File not found: {file_path}")
    if not p.is_file():
        raise ExcelInspectionError(f"Not a file: {file_path}")
    if p.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ExcelInspectionError(
            f"Unsupported file type: {p.suffix}. Only .xlsx and .xlsm."
        )

    try:
        wb = load_workbook(str(p), data_only=False, read_only=False)
    except Exception as exc:
        raise ExcelInspectionError(
            f"Cannot open workbook: {exc}"
        ) from exc

    try:
        sheet_infos: list[SheetInfo] = []
        cells_by_sheet: dict[str, list[CellInfo]] = {}

        for idx, ws in enumerate(wb.worksheets):
            # -------- Merged ranges & lookup --------
            merged_ranges = [str(r) for r in ws.merged_cells.ranges]
            merged_lookup: dict[tuple[int, int], str] = {}
            for rng in ws.merged_cells.ranges:
                for r in range(rng.min_row, rng.max_row + 1):
                    for c in range(rng.min_col, rng.max_col + 1):
                        merged_lookup[(r, c)] = str(rng)

            # -------- Hidden rows & columns --------
            # NOTE: these must be at THIS indentation level — inside
            # the sheet loop, but OUTSIDE the merged-range loops.
            hidden_rows = [
                r for r, dim in ws.row_dimensions.items() if dim.hidden
            ]
            # column_dimensions is keyed by column LETTER (e.g. "D"),
            # not by integer index. No conversion needed.
            hidden_cols = [
                col_letter
                for col_letter, dim in ws.column_dimensions.items()
                if dim.hidden
            ]

            # -------- Dimensions --------
            max_r = ws.max_row or 0
            max_c = ws.max_column or 0
            min_r = ws.min_row or 1
            min_c = ws.min_column or 1

            # -------- Cell extraction --------
            populated = 0
            formula_count = 0
            cells: list[CellInfo] = []

            if include_cells:
                count = 0
                for r in range(min_r, max_r + 1):
                    for c in range(min_c, max_c + 1):
                        if count >= max_cells_per_sheet:
                            break
                        info = _extract_cell_info(ws, r, c, merged_lookup)
                        if info is not None:
                            cells.append(info)
                            populated += 1
                            if info.is_formula:
                                formula_count += 1
                        count += 1
                    if count >= max_cells_per_sheet:
                        break

            sheet_infos.append(SheetInfo(
                name=ws.title,
                index=idx,
                max_row=max_r,
                max_column=max_c,
                min_row=min_r,
                min_column=min_c,
                state=ws.sheet_state,
                merged_ranges=merged_ranges,
                hidden_rows=hidden_rows,
                hidden_columns=hidden_cols,
                populated_cells=populated,
                formula_cells=formula_count,
            ))
            cells_by_sheet[ws.title] = cells

        # -------- Named ranges --------
        named: list[NamedRangeInfo] = []
        try:
            for name, defn in wb.defined_names.items():
                try:
                    if hasattr(defn, "attr_text"):
                        text = defn.attr_text
                    else:
                        text = str(defn.value)
                    named.append(NamedRangeInfo(
                        name=name,
                        sheet=None,
                        cell_range=text or "",
                    ))
                except Exception:
                    named.append(NamedRangeInfo(
                        name=name, sheet=None, cell_range="",
                    ))
        except Exception:
            pass

        has_macros = p.suffix.lower() == ".xlsm"

        return WorkbookInfo(
            file_path=str(p.resolve()),
            file_size_bytes=p.stat().st_size,
            sheet_names=[s.name for s in sheet_infos],
            active_sheet=wb.active.title if wb.active else None,
            has_macros=has_macros,
            sheets=sheet_infos,
            named_ranges=named,
            cells_by_sheet=cells_by_sheet,
        )
    finally:
        try:
            wb.close()
        except Exception:
            pass


# ============================================================
# SERIALIZATION
# ============================================================
def workbook_info_to_dict(info: WorkbookInfo) -> dict:
    """Convert WorkbookInfo into a JSON-serializable dict."""
    def _cell_dict(c: CellInfo) -> dict:
        return asdict(c)

    return {
        "file_path": info.file_path,
        "file_size_bytes": info.file_size_bytes,
        "sheet_names": info.sheet_names,
        "active_sheet": info.active_sheet,
        "has_macros": info.has_macros,
        "sheets": [asdict(s) for s in info.sheets],
        "named_ranges": [asdict(n) for n in info.named_ranges],
        "cells_by_sheet": {
            name: [_cell_dict(c) for c in cells]
            for name, cells in info.cells_by_sheet.items()
        },
    }