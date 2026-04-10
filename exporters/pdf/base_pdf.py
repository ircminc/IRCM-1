"""ReportLab base page templates, styles, and helpers for all PDF reports."""
from __future__ import annotations
import io
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ── Brand colors ────────────────────────────────────────────────────────────────
DARK_BLUE   = HexColor("#1F4E79")
MID_BLUE    = HexColor("#2E75B6")
LIGHT_BLUE  = HexColor("#D6E4F0")
RED         = HexColor("#C00000")
AMBER       = HexColor("#F4B942")
GREEN       = HexColor("#5BA854")
LIGHT_GRAY  = HexColor("#F2F2F2")
MED_GRAY    = HexColor("#D9D9D9")


def get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="DocTitle",
        fontSize=18, textColor=white,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        fontSize=12, textColor=DARK_BLUE,
        fontName="Helvetica-Bold",
        spaceBefore=14, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="SubTitle",
        fontSize=10, textColor=MID_BLUE,
        fontName="Helvetica-Bold",
        spaceBefore=8, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Body8",
        fontSize=8, fontName="Helvetica",
        leading=11,
    ))
    styles.add(ParagraphStyle(
        name="Body9",
        fontSize=9, fontName="Helvetica",
        leading=12,
    ))
    styles.add(ParagraphStyle(
        name="CellText",
        fontSize=7.5, fontName="Helvetica",
        leading=10, wordWrap="CJK",
    ))
    return styles


def build_table(
    data: list[list],
    col_widths: list[float] | None = None,
    has_header: bool = True,
    stripe_rows: bool = True,
    page_width: float = 7.5 * inch,
) -> Table:
    """Create a styled ReportLab Table."""
    if not data:
        return Table([[""]])

    if col_widths is None:
        n = len(data[0])
        col_widths = [page_width / n] * n

    styles_list = [
        ("BACKGROUND", (0,0), (-1,0 if has_header else -1), DARK_BLUE),
        ("TEXTCOLOR",  (0,0), (-1,0 if has_header else -1), white),
        ("FONTNAME",   (0,0), (-1,0 if has_header else -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 7.5),
        ("LEADING",    (0,0), (-1,-1), 10),
        ("ALIGN",      (0,0), (-1,-1), "LEFT"),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("GRID", (0,0), (-1,-1), 0.4, MED_GRAY),
    ]

    if has_header and stripe_rows and len(data) > 2:
        for i in range(2, len(data), 2):
            styles_list.append(("BACKGROUND", (0,i), (-1,i), LIGHT_BLUE))

    tbl = Table(data, colWidths=col_widths, repeatRows=1 if has_header else 0)
    tbl.setStyle(TableStyle(styles_list))
    return tbl


def build_kpi_row(metrics: list[tuple[str, str]], page_width: float = 7.5 * inch) -> Table:
    """
    Build a single-row KPI summary bar.
    metrics: list of (label, value) tuples
    """
    n = len(metrics)
    cell_w = page_width / n
    header_row = [Paragraph(label, ParagraphStyle(
        name=f"kpi_lbl_{i}", fontSize=7, textColor=LIGHT_BLUE,
        fontName="Helvetica", alignment=TA_CENTER,
    )) for i, (label, _) in enumerate(metrics)]
    value_row  = [Paragraph(value, ParagraphStyle(
        name=f"kpi_val_{i}", fontSize=12, textColor=white,
        fontName="Helvetica-Bold", alignment=TA_CENTER,
    )) for i, (_, value) in enumerate(metrics)]

    tbl = Table([header_row, value_row], colWidths=[cell_w]*n)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BLUE),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("LINEAFTER", (0,0), (-2,-1), 0.5, MID_BLUE),
    ]))
    return tbl


def cover_block(title: str, subtitle: str, tx_type: str, generated: str, page_width: float = 7.5*inch) -> list:
    """Return a list of Flowables for the cover block."""
    styles = get_styles()
    spacer = Spacer(1, 0.15*inch)
    badge_style = ParagraphStyle(
        "badge", fontSize=9, textColor=white, fontName="Helvetica-Bold",
        alignment=TA_CENTER, backColor=MID_BLUE,
    )
    return [
        Spacer(1, 0.1*inch),
        Table([[Paragraph(title, styles["DocTitle"])]],
              colWidths=[page_width],
              style=[("BACKGROUND",(0,0),(-1,-1),DARK_BLUE),
                     ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),12)]),
        spacer,
        Paragraph(subtitle, ParagraphStyle("sub", fontSize=10, alignment=TA_CENTER,
                                            textColor=MID_BLUE, fontName="Helvetica")),
        spacer,
        Table([[Paragraph(f"Transaction Type: {tx_type}", badge_style),
                Paragraph(f"Generated: {generated}", badge_style)]],
              colWidths=[page_width/2, page_width/2],
              style=[("BACKGROUND",(0,0),(-1,-1),MID_BLUE),
                     ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]),
        spacer,
    ]


def page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MED_GRAY)
    canvas.drawString(0.5*inch, 0.4*inch, doc.title or "ANSI X12 Report")
    canvas.drawRightString(
        doc.pagesize[0] - 0.5*inch, 0.4*inch,
        f"Page {canvas.getPageNumber()}"
    )
    canvas.restoreState()


def build_pdf(story: list, title: str = "Report", landscape_mode: bool = False) -> bytes:
    buf = io.BytesIO()
    pagesize = landscape(letter) if landscape_mode else letter
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize,
        leftMargin=0.5*inch, rightMargin=0.5*inch,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
        title=title,
    )
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return buf.getvalue()
