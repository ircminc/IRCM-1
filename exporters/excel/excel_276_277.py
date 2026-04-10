"""276/277 Excel exporter."""
from __future__ import annotations
from datetime import date
from .base_excel import (
    apply_header_row, style_data_row, auto_size_columns, freeze_header,
    new_workbook, save_workbook, DENIED_FILL, PARTIAL_FILL
)


def _fmt(val) -> str:
    if val is None: return ""
    if isinstance(val, date): return val.strftime("%m/%d/%Y")
    return str(val)


def export_276(parsed_data: dict) -> bytes:
    wb = new_workbook()
    ws = wb.create_sheet("Status Inquiries")
    hdrs = ["Trace #", "Payer ID", "Payer Name", "Provider NPI", "Provider Name",
            "Subscriber ID", "Subscriber Name", "Claim ID",
            "DOS From", "DOS To", "Request Date"]
    apply_header_row(ws, hdrs)
    for r, inq in enumerate(parsed_data.get("inquiries", []), start=2):
        row = [
            inq.get("trace_number",""), inq.get("payer_id",""), inq.get("payer_name",""),
            inq.get("provider_npi",""), inq.get("provider_name",""),
            inq.get("subscriber_id",""), inq.get("subscriber_name",""),
            inq.get("claim_id",""),
            _fmt(inq.get("dos_from")), _fmt(inq.get("dos_to")),
            _fmt(inq.get("request_date")),
        ]
        for col, val in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=val)
        style_data_row(ws, r, len(hdrs))
    auto_size_columns(ws); freeze_header(ws)
    return save_workbook(wb)


def export_277(parsed_data: dict) -> bytes:
    wb = new_workbook()
    responses = parsed_data.get("responses", [])

    # All status responses
    ws = wb.create_sheet("Status Responses")
    hdrs = ["Claim ID", "Payer Claim #", "CH Trace #", "Payer Name",
            "Provider NPI", "Subscriber Name", "Subscriber ID",
            "Status Category", "Status Code", "Status Description",
            "Effective Date", "DOS", "Amount ($)"]
    apply_header_row(ws, hdrs)
    for r, resp in enumerate(responses, start=2):
        cat = resp.get("status_category","")
        row = [
            resp.get("claim_id",""), resp.get("payer_claim_number",""),
            resp.get("clearinghouse_trace",""), resp.get("payer_name",""),
            resp.get("provider_npi",""), resp.get("subscriber_name",""),
            resp.get("subscriber_id",""), cat,
            resp.get("status_code",""), resp.get("status_description",""),
            _fmt(resp.get("effective_date")), _fmt(resp.get("dos")),
            resp.get("amount",""),
        ]
        for col, val in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=val)
        fill = DENIED_FILL if cat.startswith("F2") else (PARTIAL_FILL if cat.startswith("P") else None)
        style_data_row(ws, r, len(hdrs), fill=fill)
    auto_size_columns(ws); freeze_header(ws)

    # Pending summary
    ws2 = wb.create_sheet("Pending Claims")
    apply_header_row(ws2, ["Claim ID", "Status Category", "Status Description", "Effective Date"])
    pending = [r for r in responses if r.get("status_category","").startswith(("A","P"))]
    for r, resp in enumerate(pending, start=2):
        row = [resp.get("claim_id",""), resp.get("status_category",""),
               resp.get("status_description",""), _fmt(resp.get("effective_date"))]
        for col, val in enumerate(row, start=1):
            ws2.cell(row=r, column=col, value=val)
        style_data_row(ws2, r, 4)
    auto_size_columns(ws2); freeze_header(ws2)

    # Denied/rejected summary
    ws3 = wb.create_sheet("Denied-Rejected")
    apply_header_row(ws3, ["Claim ID", "Status Category", "Status Description", "Amount ($)", "Effective Date"])
    denied = [r for r in responses if r.get("status_category","").startswith(("F2","R"))]
    for r, resp in enumerate(denied, start=2):
        row = [resp.get("claim_id",""), resp.get("status_category",""),
               resp.get("status_description",""), resp.get("amount",""),
               _fmt(resp.get("effective_date"))]
        for col, val in enumerate(row, start=1):
            ws3.cell(row=r, column=col, value=val)
        style_data_row(ws3, r, 5, fill=DENIED_FILL)
    auto_size_columns(ws3); freeze_header(ws3)

    return save_workbook(wb)
