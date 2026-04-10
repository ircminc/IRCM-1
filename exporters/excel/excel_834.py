"""834 Enrollment Excel exporter."""
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


def export_834(parsed_data: dict) -> bytes:
    wb = new_workbook()
    members = parsed_data.get("members", [])

    # Members
    ws = wb.create_sheet("Members")
    hdrs = ["Subscriber ID", "Last Name", "First Name", "DOB", "Gender",
            "Address", "City", "State", "ZIP",
            "Maintenance Type", "Maintenance Reason",
            "Benefit Status", "Relationship Code", "COBRA Qualifier"]
    apply_header_row(ws, hdrs)
    for r, m in enumerate(members, start=2):
        row = [
            m.get("subscriber_id",""), m.get("last_name",""), m.get("first_name",""),
            _fmt(m.get("dob")), m.get("gender",""),
            m.get("address_line1",""), m.get("city",""), m.get("state",""), m.get("zip",""),
            m.get("maintenance_type_desc",""), m.get("maintenance_reason_desc",""),
            m.get("benefit_status",""), m.get("relationship_code",""), m.get("cobra_qualifier",""),
        ]
        for col, val in enumerate(row, start=1):
            ws.cell(row=r, column=col, value=val)
        style_data_row(ws, r, len(hdrs))
    auto_size_columns(ws); freeze_header(ws)

    # Coverage
    ws2 = wb.create_sheet("Coverage")
    hdrs2 = ["Subscriber ID", "Insurance Line", "Plan Description", "Coverage Level",
             "Benefit Begin", "Benefit End", "Premium ($)"]
    apply_header_row(ws2, hdrs2)
    row_num = 2
    for m in members:
        for cov in m.get("coverages", []):
            row = [
                m.get("subscriber_id",""),
                cov.get("insurance_line_code",""),
                cov.get("plan_coverage_description",""),
                cov.get("coverage_level_code",""),
                _fmt(cov.get("benefit_begin")),
                _fmt(cov.get("benefit_end")),
                cov.get("premium_amount",""),
            ]
            for col, val in enumerate(row, start=1):
                ws2.cell(row=row_num, column=col, value=val)
            style_data_row(ws2, row_num, len(hdrs2))
            row_num += 1
    auto_size_columns(ws2); freeze_header(ws2)
    return save_workbook(wb)
