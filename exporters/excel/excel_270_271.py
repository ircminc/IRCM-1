"""270/271 Excel exporter."""
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


def export_270(parsed_data: dict) -> bytes:
    wb = new_workbook()
    ws = wb.create_sheet("270 Requests")
    hdrs = ["Trace #", "Payer ID", "Payer Name", "Provider NPI",
            "Subscriber ID", "Subscriber Name", "DOB", "Gender",
            "Group Number", "Service Types", "Inquiry Date"]
    apply_header_row(ws, hdrs)
    for r, inq in enumerate(parsed_data.get("inquiries", []), start=2):
        row = [
            inq.get("hl_id",""), inq.get("payer_id",""), inq.get("payer_name",""),
            inq.get("provider_npi",""), inq.get("subscriber_id",""),
            inq.get("subscriber_name",""), _fmt(inq.get("dob")),
            inq.get("gender",""), inq.get("group_number",""),
            ", ".join(inq.get("service_types",[])),
            _fmt(inq.get("inquiry_date")),
        ]
        for col, val in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=val)
        style_data_row(ws, r, len(hdrs))
    auto_size_columns(ws); freeze_header(ws)
    return save_workbook(wb)


def export_271(parsed_data: dict) -> bytes:
    wb = new_workbook()

    # Tab 1: Responses summary
    ws = wb.create_sheet("271 Responses")
    hdrs = ["Subscriber ID", "Subscriber Name", "Payer ID", "Payer Name",
            "Plan Name", "Group #", "Coverage Active",
            "Ind Deductible ($)", "Ind Deductible Met ($)",
            "Fam Deductible ($)", "Fam Deductible Met ($)",
            "Ind OOP Max ($)", "Ind OOP Met ($)",
            "Copay ($)", "Coinsurance (%)"]
    apply_header_row(ws, hdrs)
    for r, resp in enumerate(parsed_data.get("responses", []), start=2):
        benefits = resp.get("benefits", [])

        def _find_benefit(eb_code: str, cov_level: str = "") -> dict:
            for b in benefits:
                if b.get("benefit_code") == eb_code:
                    if not cov_level or b.get("coverage_level","").startswith(cov_level):
                        return b
            return {}

        ind_ded   = _find_benefit("C", "Ind")
        fam_ded   = _find_benefit("C", "Fam")
        ind_ded_m = _find_benefit("G", "Ind")
        fam_ded_m = _find_benefit("G", "Fam")
        ind_oop   = _find_benefit("G", "Ind")
        copay_b   = _find_benefit("B")
        coins_b   = _find_benefit("A")
        row = [
            resp.get("subscriber_id",""), resp.get("subscriber_name",""),
            resp.get("payer_id",""), resp.get("payer_name",""),
            resp.get("plan_name",""), resp.get("group_number",""),
            "Yes" if resp.get("coverage_active") else ("No" if resp.get("coverage_active") is False else "Unknown"),
            ind_ded.get("monetary_amount",""), ind_ded_m.get("monetary_amount",""),
            fam_ded.get("monetary_amount",""), fam_ded_m.get("monetary_amount",""),
            ind_oop.get("monetary_amount",""), "",
            copay_b.get("monetary_amount",""), coins_b.get("percent",""),
        ]
        for col, val in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=val)
        style_data_row(ws, r, len(hdrs))
    auto_size_columns(ws); freeze_header(ws)

    # Tab 2: All benefit details
    ws = wb.create_sheet("Benefit Details")
    hdrs = ["Subscriber ID", "EB Code", "Coverage Level", "Service Type",
            "Insurance Type", "Plan Description", "Time Qualifier",
            "Amount ($)", "Percent (%)", "In/Out Network", "Message"]
    apply_header_row(ws, hdrs)
    row_num = 2
    for resp in parsed_data.get("responses", []):
        for b in resp.get("benefits", []):
            row = [
                resp.get("subscriber_id",""), b.get("benefit_code",""),
                b.get("coverage_level",""), b.get("service_type",""),
                b.get("insurance_type",""), b.get("plan_coverage_description",""),
                b.get("time_qualifier",""), b.get("monetary_amount",""),
                b.get("percent",""), b.get("in_network",""), b.get("message",""),
            ]
            for col, val in enumerate(row, start=1):
                ws.cell(row=row_num, column=col, value=val)
            style_data_row(ws, row_num, len(hdrs))
            row_num += 1
    auto_size_columns(ws); freeze_header(ws)
    return save_workbook(wb)
