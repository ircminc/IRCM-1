"""PDF report for 837P claims."""
from __future__ import annotations
from datetime import datetime, date
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, PageBreak
from .base_pdf import (
    get_styles, build_table, build_kpi_row, cover_block, build_pdf, DARK_BLUE
)


def _fmt(val) -> str:
    if val is None: return "—"
    if isinstance(val, date): return val.strftime("%m/%d/%Y")
    if isinstance(val, float): return f"${val:,.2f}"
    return str(val)


def export_pdf_837p(parsed_data: dict, cms_comparisons: list[dict] | None = None) -> bytes:
    styles = get_styles()
    claims = parsed_data.get("claims", [])
    total_billed = sum(c.get("total_billed") or 0 for c in claims)
    svc_lines    = sum(len(c.get("service_lines", [])) for c in claims)

    story = []

    # Cover
    story += cover_block(
        title="837P Professional Claims Report",
        subtitle=f"{len(claims)} claims · {svc_lines} service lines",
        tx_type="837P",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # KPI bar
    story.append(build_kpi_row([
        ("Total Claims",     str(len(claims))),
        ("Total Billed",     f"${total_billed:,.2f}"),
        ("Service Lines",    str(svc_lines)),
        ("Unique Payers",    str(len({c.get('payer_id') for c in claims} - {''}))),
        ("Unique Providers", str(len({c.get('billing_provider',{}).get('npi') for c in claims} - {''}))),
    ]))
    story.append(Spacer(1, 0.2*inch))

    # Claims table (truncated to first 500 for PDF size)
    story.append(Paragraph("Claims Summary", styles["SectionTitle"]))
    display_claims = claims[:500]
    headers = ["Claim ID", "Patient", "Subscriber ID", "Payer", "DOS From", "Total Billed", "Principal Dx"]
    rows = [headers]
    for c in display_claims:
        pat = c.get("patient",{}) or c.get("subscriber",{}) or {}
        name = f"{pat.get('last_name','')}, {pat.get('first_name','')}".strip(", ") or "—"
        dxs = c.get("diagnoses",[])
        rows.append([
            c.get("claim_id",""), name,
            c.get("subscriber",{}).get("member_id",""),
            c.get("payer_name",""),
            _fmt(c.get("dos_from")),
            _fmt(c.get("total_billed")),
            dxs[0]["code"] if dxs else "—",
        ])
    pw = 7.5 * inch
    story.append(build_table(rows, col_widths=[
        pw*0.12, pw*0.16, pw*0.12, pw*0.18, pw*0.10, pw*0.14, pw*0.10
    ]))
    if len(claims) > 500:
        story.append(Paragraph(f"(Showing first 500 of {len(claims)} claims — see Excel export for full list)", styles["Body8"]))

    # CMS Comparison section
    if cms_comparisons:
        story.append(PageBreak())
        story.append(Paragraph("CMS Rate Comparison", styles["SectionTitle"]))
        cms_hdrs = ["CPT", "Description", "Billed", "Medicare NF Rate", "Vs NF %", "Flag"]
        cms_rows = [cms_hdrs]
        for comp in cms_comparisons[:300]:
            vs = f"{comp.get('vs_non_facility_pct'):.0f}%" if comp.get("vs_non_facility_pct") is not None else "—"
            cms_rows.append([
                comp.get("cpt_hcpcs",""),
                (comp.get("description","") or "")[:40],
                _fmt(comp.get("billed_amount")),
                _fmt(comp.get("pfs_non_facility_rate")),
                vs,
                comp.get("flag",""),
            ])
        story.append(build_table(cms_rows, col_widths=[
            pw*0.08, pw*0.32, pw*0.12, pw*0.16, pw*0.12, pw*0.14
        ]))

    return build_pdf(story, title="837P Claims Report", landscape_mode=True)
