"""PDF report for 835 ERA."""
from __future__ import annotations
from datetime import datetime, date
from collections import defaultdict
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer
from .base_pdf import (
    get_styles, build_table, build_kpi_row, cover_block, build_pdf
)


def _fmt(val) -> str:
    if val is None: return "—"
    if isinstance(val, date): return val.strftime("%m/%d/%Y")
    if isinstance(val, float): return f"${val:,.2f}"
    return str(val)


def export_pdf_835(parsed_data: dict) -> bytes:
    styles   = get_styles()
    header   = parsed_data.get("header", {})
    claims   = parsed_data.get("claim_payments", [])

    total_paid   = sum(c.get("paid") or 0 for c in claims)
    total_billed = sum(c.get("billed") or 0 for c in claims)
    denied       = sum(1 for c in claims if c.get("status_code") == "4")
    denial_rate  = f"{denied/len(claims)*100:.1f}%" if claims else "0%"

    story = []
    story += cover_block(
        title="835 Electronic Remittance Advice Report",
        subtitle=f"Check/EFT: {header.get('check_eft_number','')} · {header.get('payer_name','')}",
        tx_type="835",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    story.append(build_kpi_row([
        ("Payment Date",     _fmt(header.get("payment_date"))),
        ("Total Payment",    _fmt(header.get("total_payment"))),
        ("Total Claims",     str(len(claims))),
        ("Denied Claims",    str(denied)),
        ("Denial Rate",      denial_rate),
    ]))
    story.append(Spacer(1, 0.2*inch))

    # Claim payments table
    story.append(Paragraph("Claim Payments", styles["SectionTitle"]))
    CLP_STATUS = {"1":"Processed","2":"Other","3":"Secondary","4":"Denied","22":"Reversal"}
    rows = [["CLP ID", "Status", "Patient", "Billed ($)", "Paid ($)", "Pt Resp ($)"]]
    for c in claims[:400]:
        rows.append([
            c.get("clp_id",""),
            CLP_STATUS.get(c.get("status_code",""), c.get("status_code","")),
            c.get("patient_name",""),
            _fmt(c.get("billed")),
            _fmt(c.get("paid")),
            _fmt(c.get("patient_responsibility")),
        ])
    pw = 7.5 * inch
    story.append(build_table(rows, col_widths=[
        pw*0.15, pw*0.15, pw*0.22, pw*0.16, pw*0.16, pw*0.16
    ]))

    # Denial summary
    story.append(Spacer(1, 0.15*inch))
    story.append(Paragraph("Top Denial Reason Codes", styles["SectionTitle"]))
    denial_map: dict[str, dict] = defaultdict(lambda: {"count":0,"amount":0.0,"gc":""})
    for c in claims:
        for adj in c.get("adjustments",[]):
            rc = adj.get("reason_code","")
            denial_map[rc]["count"]  += 1
            denial_map[rc]["amount"] += adj.get("amount") or 0
            denial_map[rc]["gc"]      = adj.get("group_code","")
    top = sorted(denial_map.items(), key=lambda x: -x[1]["count"])[:15]
    d_rows = [["Reason Code","Group","Count","Total Amount ($)"]]
    for rc, vals in top:
        d_rows.append([rc, vals["gc"], str(vals["count"]), f"${vals['amount']:,.2f}"])
    story.append(build_table(d_rows, col_widths=[pw*0.20,pw*0.15,pw*0.15,pw*0.20]))

    return build_pdf(story, title="835 ERA Report", landscape_mode=True)


def export_pdf_summary(
    claims_df,
    payments_df,
    denial_df,
    cms_comparisons: list[dict] | None = None,
) -> bytes:
    """Multi-file analytics summary PDF."""
    styles = get_styles()
    story  = []
    story += cover_block(
        title="Medical Billing Analytics Summary",
        subtitle="Cross-file trend analysis",
        tx_type="Multi-file",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    # Top-level KPIs
    total_billed = claims_df["total_billed"].sum() if not claims_df.empty and "total_billed" in claims_df else 0
    total_claims = len(claims_df) if not claims_df.empty else 0
    total_paid   = payments_df["paid"].sum() if not payments_df.empty and "paid" in payments_df else 0

    story.append(build_kpi_row([
        ("Total Claims",  str(total_claims)),
        ("Total Billed",  f"${total_billed:,.0f}"),
        ("Total Paid",    f"${total_paid:,.0f}"),
    ]))
    story.append(Spacer(1, 0.25*inch))

    if not denial_df.empty:
        story.append(Paragraph("Top Denial Reasons", styles["SectionTitle"]))
        rows = [["Reason Code","Description","Category","Count","Total Amount ($)","% of Denials"]]
        for _, row in denial_df.head(20).iterrows():
            rows.append([
                row.get("reason_code",""), row.get("description","")[:40],
                row.get("category",""), str(row.get("count","")),
                f"${row.get('total_amount',0):,.2f}",
                f"{row.get('pct_of_total',0):.1f}%",
            ])
        pw = 7.5 * inch
        story.append(build_table(rows, col_widths=[
            pw*0.10, pw*0.30, pw*0.14, pw*0.10, pw*0.16, pw*0.12
        ]))

    return build_pdf(story, title="Analytics Summary", landscape_mode=True)
