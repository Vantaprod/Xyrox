"""
Xyrox — Excel Filler Tests (Phase 5.3)

Every test asserts the safety rules from Master Command §17:
copy, preserve, verify, never corrupt.
"""

import pytest
from pathlib import Path
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Border, Side

from app.backend.excel.filler import (
    fill_template,
    fill_result_to_dict,
    ExcelFillError,
)


def _box() -> Border:
    s = Side()
    return Border(left=s, right=s, top=s, bottom=s)


# ============================================================
# FIXTURES
# ============================================================
@pytest.fixture
def template_xlsx(tmp_path) -> Path:
    """A report template with values, a formula, and formatting."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    ws["A1"] = "BRANDING & CONTENT"
    ws["A1"].font = Font(bold=True, size=14)

    ws["A3"] = "Installation Videos"
    ws["B3"].border = _box()
    ws["B3"].number_format = "0"

    ws["A4"] = "Total Hours"
    ws["B4"].border = _box()
    ws["B4"].number_format = "0.00"

    ws["A5"] = "Rate"
    ws["B5"].border = _box()

    # A formula we must not destroy
    ws["B6"] = "=B3*2"

    path = tmp_path / "template.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def output_dir(tmp_path) -> Path:
    d = tmp_path / "exports"
    d.mkdir()
    return d


# ============================================================
# SAFETY: ORIGINAL NEVER MODIFIED
# ============================================================
def test_original_file_never_modified(template_xlsx, output_dir):
    before = template_xlsx.read_bytes()
    fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
    )
    after = template_xlsx.read_bytes()
    assert before == after, "Original template was modified!"


def test_output_is_a_copy_not_the_original(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
    )
    out = Path(result.output_path)
    assert out.exists()
    assert out.resolve() != template_xlsx.resolve()
    assert out.stat().st_size > 0


# ============================================================
# WRITE + VERIFY
# ============================================================
def test_write_integer_and_verify(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 42},
        output_dir=str(output_dir),
    )
    assert result.ok
    assert result.written == {"B3": 42}
    v = next(v for v in result.verifications if v.coordinate == "B3")
    assert v.ok
    assert v.actual == 42


def test_write_string_and_verify(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B5": "N/A"},
        output_dir=str(output_dir),
    )
    assert result.ok
    assert result.written["B5"] == "N/A"


def test_write_float_and_verify(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B4": 12.5},
        output_dir=str(output_dir),
    )
    assert result.ok
    # float comparison via _compare_values
    v = next(v for v in result.verifications if v.coordinate == "B4")
    assert v.ok


def test_multiple_writes_at_once(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5, "B4": 10.5, "B5": "notes"},
        output_dir=str(output_dir),
    )
    assert result.ok
    assert set(result.written.keys()) == {"B3", "B4", "B5"}


# ============================================================
# FORMULA PROTECTION
# ============================================================
def test_refuses_to_overwrite_formula_by_default(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B6": 999},
        output_dir=str(output_dir),
    )
    assert not result.ok
    assert "B6" in result.skipped
    assert any("formula" in e.lower() for e in result.errors)
    # The formula must still be there
    wb = load_workbook(result.output_path)
    try:
        assert wb["Report"]["B6"].value == "=B3*2"
    finally:
        wb.close()


def test_allows_formula_overwrite_when_flagged(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B6": 999},
        output_dir=str(output_dir),
        allow_formula_overwrite=True,
    )
    assert result.ok
    wb = load_workbook(result.output_path)
    try:
        assert wb["Report"]["B6"].value == 999
    finally:
        wb.close()


# ============================================================
# PRESERVATION OF EVERYTHING ELSE
# ============================================================
def test_preserves_bold_font(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
    )
    wb = load_workbook(result.output_path)
    try:
        assert wb["Report"]["A1"].font.bold is True
        assert wb["Report"]["A1"].value == "BRANDING & CONTENT"
    finally:
        wb.close()


def test_preserves_borders(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
    )
    wb = load_workbook(result.output_path)
    try:
        cell = wb["Report"]["B3"]
        assert cell.border is not None
        assert cell.border.left is not None
    finally:
        wb.close()


def test_preserves_untouched_values(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
    )
    wb = load_workbook(result.output_path)
    try:
        assert wb["Report"]["A3"].value == "Installation Videos"
        assert wb["Report"]["A4"].value == "Total Hours"
        assert wb["Report"]["A5"].value == "Rate"
    finally:
        wb.close()


# ============================================================
# VALIDATION / HONESTY
# ============================================================
def test_verification_reported_per_cell(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 7, "B4": 3.14},
        output_dir=str(output_dir),
    )
    assert len(result.verifications) == 2
    for v in result.verifications:
        assert v.ok
        assert v.actual == v.expected


def test_output_has_description_suffix(template_xlsx, output_dir):
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
        filename_suffix="_weekly",
    )
    assert "_weekly_" in Path(result.output_path).name


# ============================================================
# ERROR HANDLING
# ============================================================
def test_missing_source_file(tmp_path, output_dir):
    with pytest.raises(ExcelFillError):
        fill_template(
            source_path=str(tmp_path / "nope.xlsx"),
            cell_values={"A1": 1},
            output_dir=str(output_dir),
        )


def test_wrong_extension(tmp_path, output_dir):
    p = tmp_path / "not_xlsx.txt"
    p.write_text("hello")
    with pytest.raises(ExcelFillError):
        fill_template(
            source_path=str(p),
            cell_values={"A1": 1},
            output_dir=str(output_dir),
        )


def test_empty_cell_values(tmp_path, output_dir):
    wb = Workbook()
    p = tmp_path / "t.xlsx"
    wb.save(p)
    with pytest.raises(ExcelFillError):
        fill_template(
            source_path=str(p),
            cell_values={},
            output_dir=str(output_dir),
        )


def test_invalid_coordinate_rejected(template_xlsx, output_dir):
    """
    Invalid coordinates are a HARD error — we refuse before touching
    any file, so no partial output is ever produced.
    """
    with pytest.raises(ExcelFillError) as exc:
        fill_template(
            source_path=str(template_xlsx),
            cell_values={"NOT_A_CELL": 5},
            output_dir=str(output_dir),
        )
    assert "Invalid cell coordinate" in str(exc.value)

    # No stray output file should have been created
    created = list(Path(output_dir).glob("*.xlsx"))
    assert created == [], f"Partial output was left behind: {created}"


def test_missing_sheet_rejected(template_xlsx, output_dir):
    with pytest.raises(ExcelFillError):
        fill_template(
            source_path=str(template_xlsx),
            cell_values={"B3": 5},
            sheet_name="DoesNotExist",
            output_dir=str(output_dir),
        )


# ============================================================
# SERIALIZATION
# ============================================================
def test_fill_result_to_dict(template_xlsx, output_dir):
    import json
    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={"B3": 5},
        output_dir=str(output_dir),
    )
    d = fill_result_to_dict(result)
    js = json.dumps(d)
    assert "B3" in js
    assert "verifications" in d
    assert d["ok"] is True


# ============================================================
# MASTER COMMAND §17 — END-TO-END
# ============================================================
def test_acceptance_fill_copy_verify_preserve(template_xlsx, output_dir):
    """
    The full §17 contract:
      1. Copy of original is created.
      2. Original is untouched.
      3. Only mapped cells written.
      4. Formulas preserved.
      5. Merged cells, formatting preserved.
      6. Re-opened, values verified.
    """
    before = template_xlsx.read_bytes()

    result = fill_template(
        source_path=str(template_xlsx),
        cell_values={
            "B3": 5,
            "B4": 12.75,
            "B5": "Delivered",
        },
        output_dir=str(output_dir),
    )

    # 1. Output exists, distinct from source
    assert Path(result.output_path).resolve() != template_xlsx.resolve()

    # 2. Original untouched
    assert template_xlsx.read_bytes() == before

    # 3. All wrote successfully
    assert result.ok
    assert set(result.written.keys()) == {"B3", "B4", "B5"}

    # 4 & 5. Re-open and confirm preservation
    wb = load_workbook(result.output_path)
    try:
        ws = wb["Report"]
        assert ws["B6"].value == "=B3*2"          # formula preserved
        assert ws["A1"].font.bold is True          # formatting preserved
        assert ws["A3"].value == "Installation Videos"
    finally:
        wb.close()

    # 6. Verifications all passed
    assert all(v.ok for v in result.verifications)