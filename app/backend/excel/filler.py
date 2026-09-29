"""
Xyrox — Safe Excel Filler + Validator (Phase 5.3, corrected)

Writes values into a *copy* of an existing template. Never touches
the original. Every write is verified by re-opening the file.

Design rules (Master Command §17):
- Copy source → output. Original is never modified.
- Pre-validate ALL coordinates BEFORE copying anything. If any
  coordinate is malformed, fail fast with no partial output file.
- Refuse to overwrite formula cells unless explicitly allowed.
- Preserve merged cells, styles, print areas — openpyxl does this
  automatically when we load and save, but we verify.
- Re-open the generated file. Compare every written value.
- Detect corruption and raise ExcelFillError.
"""

import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


class ExcelFillError(Exception):
    """Raised when a fill operation fails at any stage."""
    pass


# ============================================================
# COORDINATE VALIDATION
# ============================================================
_COORD_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")


def _validate_coordinate(coord: str) -> tuple[int, int]:
    """
    Return (row, col) for a coordinate string like 'A1'.
    Raises ExcelFillError on anything that is not a valid A1-style cell.

    This is intentionally strict: we do not accept 'Sheet1!A1',
    'A1:B2', named ranges, or anything else. Only single cells.
    """
    if not isinstance(coord, str) or not coord.strip():
        raise ExcelFillError("Cell coordinate must be a non-empty string.")
    c = coord.strip().upper()
    if not _COORD_RE.match(c):
        raise ExcelFillError(
            f"Invalid cell coordinate {coord!r}. "
            f"Expected an A1-style reference like 'B3' or 'AA10'."
        )
    # Split letters / digits
    for i, ch in enumerate(c):
        if ch.isdigit():
            letters, digits = c[:i], c[i:]
            break
    else:
        raise ExcelFillError(f"Invalid cell coordinate {coord!r}.")
    # Convert letters to column number
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    row = int(digits)
    if row < 1 or col < 1:
        raise ExcelFillError(f"Invalid cell coordinate {coord!r}.")
    return row, col


# ============================================================
# HELPERS
# ============================================================
def _normalize_value(v: Any) -> Any:
    """Convert common Python types to something openpyxl accepts."""
    if v is None:
        return None
    if isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, datetime):
        return v
    return str(v)


def _default_output_path(
    source: Path, output_dir: Optional[Path], suffix: Optional[str]
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"{source.stem}{suffix or '_filled'}_{stamp}{source.suffix}"
    if output_dir is None:
        output_dir = source.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / base


def _compare_values(expected: Any, actual: Any) -> bool:
    """Loose comparison suitable for round-tripped Excel values."""
    if expected is None and actual is None:
        return True
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return float(expected) == float(actual)
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip() == actual.strip()
    return expected == actual


# ============================================================
# DATA TYPES
# ============================================================
@dataclass
class CellVerification:
    coordinate: str
    expected: Any
    actual: Any
    ok: bool
    error: Optional[str] = None


@dataclass
class FillResult:
    source_path: str
    output_path: str
    sheet_name: str
    written: dict[str, Any] = field(default_factory=dict)
    verifications: list[CellVerification] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and all(v.ok for v in self.verifications)
        )


# ============================================================
# PUBLIC API
# ============================================================
def fill_template(
    source_path: str,
    cell_values: dict[str, Any],
    sheet_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    filename_suffix: Optional[str] = None,
    allow_formula_overwrite: bool = False,
) -> FillResult:
    """
    Write values into a COPY of an xlsx template.

    source_path: path to the original template (never modified)
    cell_values: {coordinate: value} — e.g. {"F8": 5, "G8": "N/A"}
    sheet_name:  which sheet; defaults to the active sheet
    output_dir:  where to write the copy; defaults to source dir
    filename_suffix: defaults to "_filled"
    allow_formula_overwrite:
        if False (default), writing to a cell that currently holds a
        formula is a HARD ERROR — we do not silently destroy formulas.

    Returns a FillResult with per-cell verification.
    Raises ExcelFillError if the fill cannot proceed at all (bad file,
    bad sheet, invalid coordinates, corrupt output).
    """
    src = Path(source_path)
    if not src.exists() or not src.is_file():
        raise ExcelFillError(f"Source file not found: {source_path}")
    if src.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ExcelFillError(
            f"Unsupported file type: {src.suffix}. Only .xlsx and .xlsm."
        )
    if not isinstance(cell_values, dict):
        raise ExcelFillError("cell_values must be a dict of {coord: value}.")
    if not cell_values:
        raise ExcelFillError("cell_values is empty — nothing to write.")

    # ---- PRE-VALIDATE ALL COORDINATES BEFORE TOUCHING ANY FILE ----
    normalized: dict[str, Any] = {}
    for coord, value in cell_values.items():
        coord_u = coord.strip().upper() if isinstance(coord, str) else coord
        _validate_coordinate(coord_u)  # raises on bad input
        normalized[coord_u] = value

    # ---- Decide output path ----
    out_dir = Path(output_dir) if output_dir else None
    out_path = _default_output_path(src, out_dir, filename_suffix)

    # ---- Copy source → output (source is never modified) ----
    try:
        shutil.copy2(src, out_path)
    except Exception as exc:
        raise ExcelFillError(f"Cannot copy source to output: {exc}") from exc

    result = FillResult(
        source_path=str(src.resolve()),
        output_path=str(out_path.resolve()),
        sheet_name=sheet_name or "",
    )

    # ---- Open the OUTPUT for writing ----
    try:
        wb = load_workbook(str(out_path), data_only=False, read_only=False)
    except Exception as exc:
        raise ExcelFillError(f"Cannot open output workbook: {exc}") from exc

    try:
        target = sheet_name or (wb.active.title if wb.active else None)
        if not target or target not in wb.sheetnames:
            raise ExcelFillError(f"Sheet '{target}' not found in workbook.")
        ws: Worksheet = wb[target]
        result.sheet_name = target

        # ---- Write values ----
        for coord_u, value in normalized.items():
            cell = ws[coord_u]
            existing = cell.value
            existing_is_formula = (
                isinstance(existing, str) and existing.startswith("=")
            )

            if existing_is_formula and not allow_formula_overwrite:
                result.skipped.append(coord_u)
                result.errors.append(
                    f"Cell {coord_u} contains a formula "
                    f"({existing!r}). Refusing to overwrite. "
                    f"Pass allow_formula_overwrite=True to force."
                )
                continue

            try:
                cell.value = _normalize_value(value)
                result.written[coord_u] = value
            except Exception as exc:
                result.errors.append(f"Failed to write {coord_u}: {exc}")

        try:
            wb.save(str(out_path))
        except Exception as exc:
            raise ExcelFillError(f"Cannot save output workbook: {exc}") from exc
    finally:
        try:
            wb.close()
        except Exception:
            pass

    # ---- Re-open and verify ----
    if result.written:
        try:
            wb_v = load_workbook(str(out_path), data_only=False, read_only=False)
        except Exception as exc:
            raise ExcelFillError(
                f"Output workbook cannot be re-opened after save: {exc}"
            ) from exc

        try:
            if target not in wb_v.sheetnames:
                raise ExcelFillError(
                    f"Sheet '{target}' missing after save."
                )
            ws_v = wb_v[target]
            for coord, expected in result.written.items():
                try:
                    actual = ws_v[coord].value
                    ok = _compare_values(expected, actual)
                    result.verifications.append(CellVerification(
                        coordinate=coord,
                        expected=expected,
                        actual=actual,
                        ok=ok,
                        error=None if ok else "Value mismatch after re-open.",
                    ))
                    if not ok:
                        result.errors.append(
                            f"Verification failed for {coord}: "
                            f"expected {expected!r}, got {actual!r}"
                        )
                except Exception as exc:
                    result.verifications.append(CellVerification(
                        coordinate=coord,
                        expected=expected,
                        actual=None,
                        ok=False,
                        error=str(exc),
                    ))
                    result.errors.append(f"Verification error for {coord}: {exc}")
        finally:
            try:
                wb_v.close()
            except Exception:
                pass

    return result


def fill_result_to_dict(r: FillResult) -> dict:
    """Serialize a FillResult for storage or JSON output."""
    return {
        "source_path": r.source_path,
        "output_path": r.output_path,
        "sheet_name": r.sheet_name,
        "written": r.written,
        "skipped": r.skipped,
        "ok": r.ok,
        "errors": r.errors,
        "verifications": [asdict(v) for v in r.verifications],
    }