"""
Xyrox — Report Exporters (Phase 4.4)

Take a stored Report (dict from report_builder.get_report) and
produce files in any of these formats:

    pdf     — professional, print-ready (reportlab)
    docx    — editable in Word (python-docx)
    html    — email-safe, printable (jinja2)
    md      — plain markdown (built-in)
    txt     — plain text (built-in)

Every exporter:
  1. Reads ONLY from the verified report data.
  2. Never invents numbers or sections.
  3. Writes to data/exports/ with a unique, descriptive filename.
  4. Returns the absolute path of the generated file.
  5. Verifies the file was actually written and is non-empty.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


EXPORTS_DIR = Path("data") / "exports"
VALID_FORMATS = {"pdf", "docx", "html", "md", "txt"}


class ExportError(Exception):
    """Raised when an export fails for any reason."""
    pass


# ============================================================
# HELPERS
# ============================================================
def _ensure_dir() -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORTS_DIR.resolve()


def _safe_slug(s: str) -> str:
    """Convert any string into a filesystem-safe slug."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


def _filename_for(report: dict, fmt: str) -> Path:
    """
    Build a unique, descriptive filename.
    Example: weekly_report_2026-09-22_to_2026-09-28_v1.pdf
    """
    dir_ = _ensure_dir()
    rtype = _safe_slug(report.get("report_type", "report"))
    start = report.get("period_start", "")[:10]  # YYYY-MM-DD
    end = report.get("period_end", "")[:10]
    version = report.get("version", 1)
    ext = "md" if fmt == "md" else fmt
    return dir_ / f"{rtype}_report_{start}_to_{end}_v{version}.{ext}"


def _period_label(report: dict) -> str:
    """Human-readable period label from the report dict."""
    p = (report.get("data") or {}).get("period") or {}
    if "display_date" in p:
        return p["display_date"]
    if "week_start" in p and "week_end" in p:
        return f"{p['week_start']} to {p['week_end']}"
    if "month_name" in p and "year" in p:
        return f"{p['month_name']} {p['year']}"
    start = report.get("period_start", "")[:10]
    end = report.get("period_end", "")[:10]
    return f"{start} to {end}"


def _get_section(report: dict, key: str) -> list:
    return ((report.get("data") or {}).get("sections") or {}).get(key, []) or []


def _get_verified(report: dict) -> dict:
    return ((report.get("data") or {}).get("verified_numbers") or {})


def _get_tasks_summary(report: dict) -> dict:
    return ((report.get("data") or {}).get("tasks_summary") or {})


def _get_missing(report: dict) -> list:
    return ((report.get("data") or {}).get("missing_sections") or [])


def _verify_written(path: Path, min_bytes: int = 100) -> None:
    if not path.exists():
        raise ExportError(f"File was not created: {path}")
    size = path.stat().st_size
    if size < min_bytes:
        raise ExportError(
            f"File {path.name} is suspiciously small ({size} bytes)."
        )


# ============================================================
# MARKDOWN
# ============================================================
def export_markdown(report: dict) -> str:
    """Export to Markdown. Returns absolute path."""
    lines: list[str] = []
    rtype = report.get("report_type", "report").capitalize()
    lines.append(f"# Xyrox — {rtype} Report")
    lines.append("")
    lines.append(f"**Period:** {_period_label(report)}")
    lines.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    v = _get_verified(report)
    lines.append("## Verified Numbers")
    lines.append("")
    lines.append(f"- Total work logs: **{v.get('total_logs', 0)}**")
    lines.append(f"- Total minutes: **{v.get('total_minutes', 0)}**")
    lines.append(f"- Total hours: **{v.get('total_hours', 0.0)}**")
    lines.append(f"- Distinct customers: **{v.get('distinct_customer_count', 0)}**")
    sb = v.get("status_breakdown") or {}
    if sb:
        lines.append("- Status breakdown:")
        for k, n in sorted(sb.items()):
            lines.append(f"  - {k}: {n}")
    lines.append("")

    ts = _get_tasks_summary(report)
    if ts:
        lines.append("## Task Summary")
        lines.append("")
        lines.append(f"- Total tasks: **{ts.get('total', 0)}**")
        lines.append(f"- Overdue: **{ts.get('overdue', 0)}**")
        lines.append("")

    lines.append("## Work Completed")
    lines.append("")
    completed = _get_section(report, "work_completed")
    if completed:
        for w in completed:
            parts = [f"- **{w.get('activity', '')}**"]
            if w.get("customer"):
                parts.append(f" (customer: {w['customer']})")
            if w.get("duration_minutes"):
                parts.append(f" — {w['duration_minutes']} min")
            lines.append("".join(parts))
    else:
        lines.append("_NOT PROVIDED_")
    lines.append("")

    lines.append("## Work In Progress")
    lines.append("")
    wip = _get_section(report, "work_in_progress")
    if wip:
        for w in wip:
            parts = [f"- {w.get('activity', '')}"]
            if w.get("customer"):
                parts.append(f" (customer: {w['customer']})")
            lines.append("".join(parts))
    else:
        lines.append("_NOT PROVIDED_")
    lines.append("")

    lines.append("## Outstanding Tasks")
    lines.append("")
    outstanding = _get_section(report, "outstanding_tasks")
    if outstanding:
        for t in outstanding:
            lines.append(f"- [{t.get('priority', '?')}] {t.get('title', '')} ({t.get('status', '')})")
    else:
        lines.append("_NOT PROVIDED_")
    lines.append("")

    missing = _get_missing(report)
    if missing:
        lines.append("## Sections Not Provided")
        lines.append("")
        for m in missing:
            lines.append(f"- {m.replace('_', ' ').title()}: _NOT PROVIDED_")
        lines.append("")

    path = _filename_for(report, "md")
    path.write_text("\n".join(lines), encoding="utf-8")
    _verify_written(path)
    return str(path)


# ============================================================
# PLAIN TEXT
# ============================================================
def export_text(report: dict) -> str:
    """Export to plain text (WhatsApp/email body friendly)."""
    md = export_markdown(report)
    text = Path(md).read_text(encoding="utf-8")
    # Strip markdown emphasis chars
    for ch in ("#", "*", "_", "`"):
        text = text.replace(ch, "")
    path = _filename_for(report, "txt")
    path.write_text(text, encoding="utf-8")
    _verify_written(path)
    return str(path)


# ============================================================
# PDF
# ============================================================
def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="XyroxTitle", parent=styles["Title"],
        fontSize=20, leading=26, textColor=colors.HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        name="XyroxH2", parent=styles["Heading2"],
        fontSize=14, leading=18, spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#16213e"),
    ))
    styles.add(ParagraphStyle(
        name="XyroxBody", parent=styles["BodyText"],
        fontSize=10, leading=14,
    ))
    styles.add(ParagraphStyle(
        name="XyroxMissing", parent=styles["BodyText"],
        fontSize=10, leading=14, textColor=colors.HexColor("#888888"),
        fontName="Helvetica-Oblique",
    ))
    return styles


def export_pdf(report: dict) -> str:
    """Export to a clean, professional PDF. Returns absolute path."""
    path = _filename_for(report, "pdf")
    styles = _pdf_styles()
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Xyrox {report.get('report_type', '')} report",
        author="Xyrox",
    )
    story = []

    story.append(Paragraph(
        f"Xyrox — {(report.get('report_type') or 'report').capitalize()} Report",
        styles["XyroxTitle"],
    ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"<b>Period:</b> {_period_label(report)}", styles["XyroxBody"]))
    story.append(Paragraph(
        f"<b>Generated:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        styles["XyroxBody"],
    ))
    story.append(Spacer(1, 0.5 * cm))

    v = _get_verified(report)
    story.append(Paragraph("Verified Numbers", styles["XyroxH2"]))
    rows = [
        ["Metric", "Value"],
        ["Total work logs", str(v.get("total_logs", 0))],
        ["Total minutes", str(v.get("total_minutes", 0))],
        ["Total hours", str(v.get("total_hours", 0.0))],
        ["Distinct customers", str(v.get("distinct_customer_count", 0))],
    ]
    t = Table(rows, colWidths=[8 * cm, 6 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5 * cm))

    ts = _get_tasks_summary(report)
    if ts:
        story.append(Paragraph("Task Summary", styles["XyroxH2"]))
        story.append(Paragraph(f"Total: {ts.get('total', 0)}  |  Overdue: {ts.get('overdue', 0)}", styles["XyroxBody"]))

    story.append(Paragraph("Work Completed", styles["XyroxH2"]))
    completed = _get_section(report, "work_completed")
    if completed:
        for w in completed:
            text = f"• <b>{w.get('activity', '')}</b>"
            if w.get("customer"):
                text += f" — {w['customer']}"
            if w.get("duration_minutes"):
                text += f" ({w['duration_minutes']} min)"
            story.append(Paragraph(text, styles["XyroxBody"]))
    else:
        story.append(Paragraph("NOT PROVIDED", styles["XyroxMissing"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("Work In Progress", styles["XyroxH2"]))
    wip = _get_section(report, "work_in_progress")
    if wip:
        for w in wip:
            text = f"• {w.get('activity', '')}"
            if w.get("customer"):
                text += f" — {w['customer']}"
            story.append(Paragraph(text, styles["XyroxBody"]))
    else:
        story.append(Paragraph("NOT PROVIDED", styles["XyroxMissing"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("Outstanding Tasks", styles["XyroxH2"]))
    outstanding = _get_section(report, "outstanding_tasks")
    if outstanding:
        for t in outstanding:
            story.append(Paragraph(
                f"• [{t.get('priority', '?')}] {t.get('title', '')}",
                styles["XyroxBody"],
            ))
    else:
        story.append(Paragraph("NOT PROVIDED", styles["XyroxMissing"]))
    story.append(Spacer(1, 0.3 * cm))

    missing = _get_missing(report)
    if missing:
        story.append(Paragraph("Sections Not Provided", styles["XyroxH2"]))
        for m in missing:
            story.append(Paragraph(
                f"• {m.replace('_', ' ').title()}: NOT PROVIDED",
                styles["XyroxMissing"],
            ))

    doc.build(story)
    _verify_written(path, min_bytes=500)  # PDFs with content are > 500 bytes
    return str(path)


# ============================================================
# DOCX
# ============================================================
def export_docx(report: dict) -> str:
    """Export to a Word document. Returns absolute path."""
    path = _filename_for(report, "docx")
    doc = Document()

    # Title
    h = doc.add_heading(f"Xyrox — {(report.get('report_type') or 'report').capitalize()} Report", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT

    doc.add_paragraph(f"Period: {_period_label(report)}")
    doc.add_paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    v = _get_verified(report)
    doc.add_heading("Verified Numbers", level=1)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text = "Metric"
    hdr[1].text = "Value"
    for label, val in [
        ("Total work logs", v.get("total_logs", 0)),
        ("Total minutes", v.get("total_minutes", 0)),
        ("Total hours", v.get("total_hours", 0.0)),
        ("Distinct customers", v.get("distinct_customer_count", 0)),
    ]:
        row = table.add_row().cells
        row[0].text = label
        row[1].text = str(val)

    doc.add_heading("Work Completed", level=1)
    completed = _get_section(report, "work_completed")
    if completed:
        for w in completed:
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(w.get("activity", ""))
            run.bold = True
            if w.get("customer"):
                p.add_run(f" — {w['customer']}")
            if w.get("duration_minutes"):
                p.add_run(f" ({w['duration_minutes']} min)")
    else:
        doc.add_paragraph("NOT PROVIDED").italic = True

    doc.add_heading("Work In Progress", level=1)
    wip = _get_section(report, "work_in_progress")
    if wip:
        for w in wip:
            doc.add_paragraph(w.get("activity", ""), style="List Bullet")
    else:
        doc.add_paragraph("NOT PROVIDED")

    doc.add_heading("Outstanding Tasks", level=1)
    outstanding = _get_section(report, "outstanding_tasks")
    if outstanding:
        for t in outstanding:
            doc.add_paragraph(
                f"[{t.get('priority', '?')}] {t.get('title', '')}",
                style="List Bullet",
            )
    else:
        doc.add_paragraph("NOT PROVIDED")

    missing = _get_missing(report)
    if missing:
        doc.add_heading("Sections Not Provided", level=1)
        for m in missing:
            doc.add_paragraph(
                f"{m.replace('_', ' ').title()}: NOT PROVIDED",
                style="List Bullet",
            )

    doc.save(str(path))
    _verify_written(path, min_bytes=1000)
    return str(path)


# ============================================================
# HTML
# ============================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Xyrox Report — {period}</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif;
        max-width: 780px; margin: 2rem auto; padding: 0 1rem;
        color: #1a1a2e; line-height: 1.55; }}
h1 {{ border-bottom: 3px solid #16213e; padding-bottom: .3rem; }}
h2 {{ color: #16213e; margin-top: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: .5rem .75rem; text-align: left; }}
th {{ background: #16213e; color: white; }}
tr:nth-child(even) {{ background: #f5f5f5; }}
.missing {{ color: #888; font-style: italic; }}
ul {{ padding-left: 1.4rem; }}
</style>
</head>
<body>
<h1>Xyrox — {rtype} Report</h1>
<p><b>Period:</b> {period}<br>
<b>Generated:</b> {generated}</p>

<h2>Verified Numbers</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total work logs</td><td>{total_logs}</td></tr>
<tr><td>Total minutes</td><td>{total_minutes}</td></tr>
<tr><td>Total hours</td><td>{total_hours}</td></tr>
<tr><td>Distinct customers</td><td>{distinct_customers}</td></tr>
</table>

<h2>Work Completed</h2>
{completed_html}

<h2>Work In Progress</h2>
{wip_html}

<h2>Outstanding Tasks</h2>
{outstanding_html}

{missing_html}
</body>
</html>
"""


def _ul(items: list[str], missing_label: str = "NOT PROVIDED") -> str:
    if not items:
        return f'<p class="missing">{missing_label}</p>'
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def export_html(report: dict) -> str:
    """Export to standalone HTML. Returns absolute path."""
    v = _get_verified(report)
    completed = [
        (f"<b>{w.get('activity', '')}</b>"
         + (f" — {w['customer']}" if w.get("customer") else "")
         + (f" ({w['duration_minutes']} min)" if w.get("duration_minutes") else ""))
        for w in _get_section(report, "work_completed")
    ]
    wip = [
        (w.get("activity", "") + (f" — {w['customer']}" if w.get("customer") else ""))
        for w in _get_section(report, "work_in_progress")
    ]
    outstanding = [
        f"[{t.get('priority', '?')}] {t.get('title', '')}"
        for t in _get_section(report, "outstanding_tasks")
    ]
    missing = _get_missing(report)
    missing_html = ""
    if missing:
        missing_html = (
            "<h2>Sections Not Provided</h2>"
            + _ul([f"{m.replace('_', ' ').title()}: NOT PROVIDED" for m in missing])
        )

    html = HTML_TEMPLATE.format(
        period=_period_label(report),
        rtype=(report.get("report_type") or "report").capitalize(),
        generated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        total_logs=v.get("total_logs", 0),
        total_minutes=v.get("total_minutes", 0),
        total_hours=v.get("total_hours", 0.0),
        distinct_customers=v.get("distinct_customer_count", 0),
        completed_html=_ul(completed),
        wip_html=_ul(wip),
        outstanding_html=_ul(outstanding),
        missing_html=missing_html,
    )
    path = _filename_for(report, "html")
    path.write_text(html, encoding="utf-8")
    _verify_written(path, min_bytes=500)
    return str(path)


# ============================================================
# DISPATCH
# ============================================================
def export_report(report: dict, fmt: str) -> str:
    """
    Export a report in the given format.
    Returns the absolute path of the generated file.
    Raises ExportError if fmt is invalid or the export fails.
    """
    if not report or not isinstance(report, dict):
        raise ExportError("report must be a non-empty dict.")
    fmt = (fmt or "").strip().lower()
    if fmt not in VALID_FORMATS:
        raise ExportError(
            f"format must be one of {sorted(VALID_FORMATS)}, got {fmt!r}."
        )
    dispatch = {
        "pdf": export_pdf,
        "docx": export_docx,
        "html": export_html,
        "md": export_markdown,
        "txt": export_text,
    }
    try:
        return dispatch[fmt](report)
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(f"Failed to export {fmt}: {exc}") from exc