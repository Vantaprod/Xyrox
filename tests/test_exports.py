"""
Xyrox — Export Tests (Phase 4.4)

Real exports to real files. Verifies each format is written and
contains the expected content. Uses an isolated exports directory.
"""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import report_builder
from app.backend.services import calculations as calc
from app.backend.exports import exporters
from app.backend.exports.exporters import export_report, ExportError
from app.backend.tools import reports as reports_module
from app.backend.tools import build_default_registry
from app.backend.tools.base import ToolValidationError


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "exports_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Redirect DB
    monkeypatch.setattr(calc, "SessionLocal", TestSession)
    monkeypatch.setattr(report_builder, "SessionLocal", TestSession)

    # Redirect exports directory into the tmp folder
    export_dir = tmp_path / "exports"
    monkeypatch.setattr(exporters, "EXPORTS_DIR", export_dir)

    yield TestSession

    engine.dispose()


def _sample_report() -> dict:
    """Build a real report via the builder so tests hit the real path."""
    r = build_default_registry()
    return r.execute("create_weekly_report", {})


# ============================================================
# REGISTRATION
# ============================================================
def test_export_tool_registered():
    r = build_default_registry()
    assert "export_report" in r


def test_registry_schema_contains_export_tool():
    r = build_default_registry()
    names = {t["function"]["name"] for t in r.to_ai_schema()}
    assert "export_report" in names


# ============================================================
# FORMAT-SPECIFIC EXPORTS
# ============================================================
def test_export_markdown_creates_file():
    report = _sample_report()
    path = export_report(report, "md")
    p = Path(path)
    assert p.exists()
    assert p.stat().st_size > 100
    text = p.read_text(encoding="utf-8")
    assert "Xyrox" in text
    assert "Verified Numbers" in text


def test_export_text_creates_file():
    report = _sample_report()
    path = export_report(report, "txt")
    p = Path(path)
    assert p.exists()
    assert p.stat().st_size > 100
    text = p.read_text(encoding="utf-8")
    assert "Xyrox" in text
    # No markdown syntax leaked
    assert "##" not in text


def test_export_pdf_creates_file():
    report = _sample_report()
    path = export_report(report, "pdf")
    p = Path(path)
    assert p.exists()
    assert p.stat().st_size > 500
    # PDF files start with the magic bytes %PDF-
    header = p.read_bytes()[:4]
    assert header == b"%PDF"


def test_export_docx_creates_file():
    report = _sample_report()
    path = export_report(report, "docx")
    p = Path(path)
    assert p.exists()
    assert p.stat().st_size > 1000
    # DOCX is a ZIP archive — first two bytes are PK
    header = p.read_bytes()[:2]
    assert header == b"PK"


def test_export_html_creates_file():
    report = _sample_report()
    path = export_report(report, "html")
    p = Path(path)
    assert p.exists()
    assert p.stat().st_size > 200
    text = p.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in text
    assert "Xyrox" in text


# ============================================================
# CONTENT CORRECTNESS
# ============================================================
def test_pdf_contains_expected_text():
    """Read the PDF back and verify it says what we expect."""
    from pypdf import PdfReader
    report = _sample_report()
    path = export_report(report, "pdf")
    reader = PdfReader(path)
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Xyrox" in text
    assert "Verified Numbers" in text


def test_docx_contains_expected_text():
    from docx import Document
    report = _sample_report()
    path = export_report(report, "docx")
    doc = Document(path)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Xyrox" in text


# ============================================================
# VALIDATION
# ============================================================
def test_export_rejects_invalid_format():
    report = _sample_report()
    with pytest.raises(ExportError):
        export_report(report, "exe")


def test_export_rejects_empty_report():
    with pytest.raises(ExportError):
        export_report({}, "pdf")


def test_tool_rejects_missing_report():
    r = build_default_registry()
    with pytest.raises(ToolValidationError):
        r.execute("export_report", {"report_id": 999999})


def test_tool_rejects_bad_format():
    r = build_default_registry()
    rep = r.execute("create_daily_report", {})
    with pytest.raises(ToolValidationError):
        r.execute("export_report", {"report_id": rep["report_id"], "format": "doc"})


# ============================================================
# END-TO-END VIA TOOLS
# ============================================================
def test_export_tool_returns_path():
    r = build_default_registry()
    rep = r.execute("create_daily_report", {})
    result = r.execute("export_report", {
        "report_id": rep["report_id"],
        "format": "pdf",
    })
    assert "file_path" in result
    p = Path(result["file_path"])
    assert p.exists()
    assert p.stat().st_size > 500


def test_all_formats_export_same_report():
    """The same report can be exported to all five formats."""
    r = build_default_registry()
    rep = r.execute("create_weekly_report", {})
    report_id = rep["report_id"]
    for fmt in ("pdf", "docx", "html", "md", "txt"):
        result = r.execute("export_report", {
            "report_id": report_id, "format": fmt,
        })
        p = Path(result["file_path"])
        assert p.exists(), f"{fmt} file not created"
        assert p.stat().st_size > 100, f"{fmt} file too small"


# ============================================================
# MASTER COMMAND §53, TEST 4 — human-usable output
# ============================================================
def test_acceptance_generate_and_export_weekly_report():
    """
    'Generate my weekly report as PDF.'
    Real report from real records → real PDF on disk.
    """
    # Insert some real work
    r = build_default_registry()
    db = calc.SessionLocal()
    try:
        from app.backend.models.models import WorkLog
        from datetime import datetime, timezone
        user = calc._get_default_user(db)
        for i in range(3):
            db.add(WorkLog(
                work_date=datetime.now(timezone.utc),
                activity=f"Task {i+1}",
                status="completed",
                customer="Promise",
                duration_minutes=30,
                user_id=user.id,
                source="chat",
                ai_confidence="high",
            ))
        db.commit()
    finally:
        db.close()

    # Generate report
    rep = r.execute("create_weekly_report", {})
    assert rep["verified_numbers"]["total_logs"] >= 3

    # Export to PDF
    export = r.execute("export_report", {
        "report_id": rep["report_id"],
        "format": "pdf",
    })
    p = Path(export["file_path"])
    assert p.exists()
    assert p.read_bytes()[:4] == b"%PDF"