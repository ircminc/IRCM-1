"""820 Payment Excel exporter."""
from __future__ import annotations
from datetime import date
from .base_excel import (
    apply_header_row, style_data_row, auto_size_columns, freeze_header,
    new_workbook, save_workbook
)


def _fmt(val) -> str:
    if val is None: return ""
    if isinstance(val, date): return val.strftime("%m/%d/%Y")
    return str(val)


def export_820(parsed_data: dict) -> bytes:
    wb = new_workbook()
    header      = parsed_data.get("header", {})
    remittances = parsed_data.get("remittances", [])
    adjustments = parsed_data.get("adjustments", [])

    # Summary
    ws = wb.create_sheet("Payment Summary")
    apply_header_row(ws, ["Metric", "Value"])
    rows = [
        ("Trace / Check #",    header.get("trace_number","")),
        ("Payment Date",        _fmt(header.get("payment_date"))),
        ("Payment Method",      header.get("payment_method","")),
        ("Total Amount ($)",    header.get("payment_amount","")),
        ("Payer Name",          header.get("payer_name","")),
        ("Payee Name",          header.get("payee_name","")),
        ("Payee ID",            header.get("payee_id","")),
    ]
    for r, (k,v) in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=k)
        ws.cell(row=r, column=2, value=v)
        style_data_row(ws, r, 2)
    auto_size_columns(ws); freeze_header(ws)

    # Remittance detail
    ws2 = wb.create_sheet("Remittance Detail")
    hdrs = ["Entity Number", "Entity ID", "Entity Name",
            "Group/Policy #", "Invoice #", "Amount Paid ($)", "References"]
    apply_header_row(ws2, hdrs)
    for r, rem in enumerate(remittances, start=2):
        refs = "; ".join(f"{ref['qualifier']}:{ref['value']}" for ref in rem.get("references",[]))
        row = [
            rem.get("entity_number",""), rem.get("entity_id",""), rem.get("entity_name",""),
            rem.get("group_policy_number",""), rem.get("invoice_number",""),
            rem.get("amount_paid",""), refs,
        ]
        for col, val in enumerate(row, start=1):
            ws2.cell(row=r, column=col, value=val)
        style_data_row(ws2, r, len(hdrs))
    auto_size_columns(ws2); freeze_header(ws2)

    # Adjustments
    if adjustments:
        ws3 = wb.create_sheet("Adjustments")
        hdrs3 = ["Reason Code", "Amount ($)", "Reference ID"]
        apply_header_row(ws3, hdrs3)
        for r, adj in enumerate(adjustments, start=2):
            row = [adj.get("reason_code",""), adj.get("amount",""), adj.get("reference_id","")]
            for col, val in enumerate(row, start=1):
                ws3.cell(row=r, column=col, value=val)
            style_data_row(ws3, r, len(hdrs3))
        auto_size_columns(ws3); freeze_header(ws3)

    return save_workbook(wb)
