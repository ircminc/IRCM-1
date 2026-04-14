"""Export parsed data to Excel or PDF."""
import streamlit as st
from storage.file_store import list_files, ensure_db
import io

st.title("📊 Export to Excel / PDF")

ensure_db()
files = list_files()
if not files:
    st.info("No files parsed yet. Go to Upload & Parse first.")
    st.stop()

file_opts = {f"{f['filename']} (#{f['id']} · {f['tx_type']})": f for f in files}
selected_label = st.selectbox("Select file to export:", list(file_opts.keys()))
file_info = file_opts[selected_label]
tx_type   = file_info["tx_type"]

include_cms = False
if tx_type == "837P":
    include_cms = st.toggle("Include CMS Rate Comparison tab", value=True,
                             help="Requires CMS PFS data to be loaded (may take a moment on first use)")

fmt = st.radio("Export format:", ["Excel (.xlsx)", "PDF (.pdf)"], horizontal=True)

if st.button("Generate Export", type="primary"):
    # Re-parse from DB data
    if tx_type == "837P":
        from analytics.aggregator import get_claims_df, get_service_lines_df
        from storage.models_db import Claim837, ServiceLine837
        from storage.database import get_session
        with get_session() as session:
            db_claims = session.query(Claim837).filter(Claim837.file_id == file_info["id"]).all()
            claims_list = []
            for c in db_claims:
                sl_rows = session.query(ServiceLine837).filter(ServiceLine837.claim_id == c.id).all()
                claims_list.append({
                    "claim_id": c.claim_id, "total_billed": c.total_billed,
                    "place_of_service": c.place_of_service,
                    "claim_frequency": c.claim_frequency,
                    "claim_filing_indicator": c.claim_filing_indicator,
                    "group_number": c.group_number,
                    "payer_id": c.payer_id, "payer_name": c.payer_name,
                    "billing_provider": {"npi": c.billing_provider_npi, "last_name_org": c.billing_provider_name},
                    "subscriber": {"last_name": c.subscriber_last, "first_name": c.subscriber_first,
                                   "member_id": c.subscriber_id},
                    "patient": {"last_name": c.patient_last, "first_name": c.patient_first,
                                "dob": c.patient_dob},
                    "dos_from": c.dos_from, "dos_to": c.dos_to,
                    "diagnoses": [{"qualifier":"ABK","code": c.principal_dx}] if c.principal_dx else [],
                    "service_lines": [
                        {"line_number": sl.line_number, "cpt_hcpcs": sl.cpt_hcpcs,
                         "modifier_1": sl.modifier_1, "modifier_2": sl.modifier_2,
                         "billed_amount": sl.billed_amount, "units": sl.units,
                         "place_of_service": sl.place_of_service,
                         "diagnosis_pointers": sl.diagnosis_pointers, "ndc": sl.ndc,
                         "rendering_provider_npi": sl.rendering_provider_npi,
                         "rendering_provider_name": ""}
                        for sl in sl_rows
                    ],
                    "claim_note": c.claim_note,
                    "payer_claim_number": c.payer_claim_number,
                })
        parsed_data = {"claims": claims_list, "providers": []}
        cms_comps = None
        if include_cms:
            with st.spinner("Loading CMS rates..."):
                try:
                    from cms_rates.rate_comparator import compare_claims
                    cms_comps = compare_claims(claims_list)
                    st.info(f"CMS rates loaded: {len(cms_comps)} line comparisons")
                except Exception as e:
                    st.warning(f"CMS rates unavailable: {e}")
    elif tx_type == "835":
        from storage.models_db import ClaimPayment835, Adjustment835
        from storage.database import get_session
        from storage.file_store import list_files
        with get_session() as session:
            db_pays = session.query(ClaimPayment835).filter(ClaimPayment835.file_id == file_info["id"]).all()
            pay_list = []
            payer_name = ""
            payment_date = None
            for cp in db_pays:
                payer_name = cp.payer_name
                payment_date = cp.payment_date
                adjs = session.query(Adjustment835).filter(Adjustment835.payment_id == cp.id, Adjustment835.level == "claim").all()
                pay_list.append({
                    "clp_id": cp.clp_id, "status_code": cp.status_code,
                    "billed": cp.billed, "paid": cp.paid,
                    "patient_responsibility": cp.patient_responsibility,
                    "claim_filing_indicator": cp.claim_filing_indicator,
                    "payer_claim_number": cp.payer_claim_number,
                    "patient_name": cp.patient_name, "patient_id": "",
                    "adjustments": [{"group_code": a.group_code, "group_description": "", "reason_code": a.reason_code, "amount": a.amount} for a in adjs],
                    "services": [],
                })
        parsed_data = {
            "header": {"payer_name": payer_name, "payment_date": payment_date,
                       "total_payment": sum(p.get("paid") or 0 for p in pay_list),
                       "check_eft_number": ""},
            "claim_payments": pay_list,
            "provider_adjustments": [],
        }
        cms_comps = None
    else:
        st.warning(f"Export from DB not yet fully implemented for {tx_type}. Re-upload and parse the file to export directly.")
        st.stop()

    with st.spinner("Generating export..."):
        try:
            if "Excel" in fmt:
                from exporters.excel.excel_dispatch import export_to_excel
                xlsx_bytes = export_to_excel(tx_type, parsed_data, cms_comps)
                fname = f"{file_info['filename'].rsplit('.',1)[0]}_{tx_type}.xlsx"
                st.download_button(
                    label=f"⬇️ Download {fname}",
                    data=xlsx_bytes,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                from exporters.pdf.pdf_dispatch import export_to_pdf
                pdf_bytes = export_to_pdf(tx_type, parsed_data, cms_comps)
                fname = f"{file_info['filename'].rsplit('.',1)[0]}_{tx_type}.pdf"
                st.download_button(
                    label=f"⬇️ Download {fname}",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                )
            st.success("Export ready!")
        except Exception as e:
            st.error(f"Export failed: {e}")
            import traceback
            st.code(traceback.format_exc())
