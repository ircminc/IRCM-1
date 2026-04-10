"""
Persist parsed EDI data to the SQLite database.
Handles all 8 TX types via a single save_parsed_file() entry point.
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from config import settings
from .database import get_session, init_db
from .models_db import ParsedFile, Claim837, ServiceLine837, ClaimPayment835, Adjustment835

logger = logging.getLogger(__name__)


def ensure_db():
    init_db()


def save_parsed_file(
    filename: str,
    tx_type: str,
    parsed_result: dict,
    file_size: int = 0,
) -> int:
    """
    Save a parsed EDI file to the database.
    Returns the file ID.
    """
    ensure_db()
    with get_session() as session:
        pf = ParsedFile(
            filename=filename,
            tx_type=tx_type,
            upload_ts=datetime.utcnow(),
            parsed_ts=datetime.utcnow(),
            status="parsed",
            file_size_bytes=file_size,
        )
        session.add(pf)
        session.flush()  # get pf.id

        data = parsed_result.get("data", {})
        record_count = 0

        if tx_type == "837P":
            record_count = _save_837p(session, pf.id, data)
        elif tx_type == "835":
            record_count = _save_835(session, pf.id, data)

        pf.record_count = record_count
        return pf.id


def _save_837p(session, file_id: int, data: dict) -> int:
    claims = data.get("claims", [])
    for c in claims:
        dxs = c.get("diagnoses", [])
        principal_dx = dxs[0]["code"] if dxs else ""

        claim_row = Claim837(
            file_id=file_id,
            claim_id=c.get("claim_id",""),
            total_billed=c.get("total_billed"),
            place_of_service=c.get("place_of_service",""),
            claim_frequency=c.get("claim_frequency",""),
            claim_filing_indicator=c.get("claim_filing_indicator",""),
            group_number=c.get("group_number",""),
            payer_id=c.get("payer_id",""),
            payer_name=c.get("payer_name",""),
            billing_provider_npi=c.get("billing_provider",{}).get("npi",""),
            billing_provider_name=c.get("billing_provider",{}).get("last_name_org",""),
            subscriber_id=c.get("subscriber",{}).get("member_id",""),
            subscriber_last=c.get("subscriber",{}).get("last_name",""),
            subscriber_first=c.get("subscriber",{}).get("first_name",""),
            patient_last=c.get("patient",{}).get("last_name","") or c.get("subscriber",{}).get("last_name",""),
            patient_first=c.get("patient",{}).get("first_name","") or c.get("subscriber",{}).get("first_name",""),
            patient_dob=c.get("patient",{}).get("dob") or c.get("subscriber",{}).get("dob"),
            dos_from=c.get("dos_from"),
            dos_to=c.get("dos_to"),
            principal_dx=principal_dx,
            claim_note=c.get("claim_note",""),
            payer_claim_number=c.get("payer_claim_number",""),
        )
        session.add(claim_row)
        session.flush()

        for sl in c.get("service_lines", []):
            session.add(ServiceLine837(
                claim_id=claim_row.id,
                line_number=sl.get("line_number",""),
                cpt_hcpcs=sl.get("cpt_hcpcs",""),
                modifier_1=sl.get("modifier_1",""),
                modifier_2=sl.get("modifier_2",""),
                billed_amount=sl.get("billed_amount"),
                units=sl.get("units",""),
                place_of_service=sl.get("place_of_service",""),
                diagnosis_pointers=sl.get("diagnosis_pointers",""),
                ndc=sl.get("ndc",""),
                rendering_provider_npi=sl.get("rendering_provider_npi",""),
            ))
    return len(claims)


def _save_835(session, file_id: int, data: dict) -> int:
    header = data.get("header", {})
    payer_id   = header.get("payer_id","")
    payer_name = header.get("payer_name","")
    payment_date = header.get("payment_date")

    claims = data.get("claim_payments", [])
    for c in claims:
        cp = ClaimPayment835(
            file_id=file_id,
            clp_id=c.get("clp_id",""),
            status_code=c.get("status_code",""),
            billed=c.get("billed"),
            paid=c.get("paid"),
            patient_responsibility=c.get("patient_responsibility"),
            claim_filing_indicator=c.get("claim_filing_indicator",""),
            payer_claim_number=c.get("payer_claim_number",""),
            payer_id=payer_id,
            payer_name=payer_name,
            patient_name=c.get("patient_name",""),
            payment_date=payment_date,
        )
        session.add(cp)
        session.flush()

        # Claim-level adjustments
        for adj in c.get("adjustments", []):
            session.add(Adjustment835(
                payment_id=cp.id, file_id=file_id,
                group_code=adj.get("group_code",""),
                reason_code=adj.get("reason_code",""),
                amount=adj.get("amount"),
                level="claim", cpt_hcpcs="",
            ))
        # Service-level adjustments
        for svc in c.get("services", []):
            for adj in svc.get("adjustments", []):
                session.add(Adjustment835(
                    payment_id=cp.id, file_id=file_id,
                    group_code=adj.get("group_code",""),
                    reason_code=adj.get("reason_code",""),
                    amount=adj.get("amount"),
                    level="service",
                    cpt_hcpcs=svc.get("cpt_hcpcs",""),
                ))
    return len(claims)


def list_files(tx_type: str | None = None) -> list[dict]:
    ensure_db()
    with get_session() as session:
        q = session.query(ParsedFile)
        if tx_type:
            q = q.filter(ParsedFile.tx_type == tx_type)
        files = q.order_by(ParsedFile.upload_ts.desc()).all()
        return [
            {
                "id": f.id, "filename": f.filename, "tx_type": f.tx_type,
                "upload_ts": f.upload_ts, "status": f.status,
                "record_count": f.record_count,
                "file_size_bytes": f.file_size_bytes,
            }
            for f in files
        ]


def delete_file(file_id: int):
    ensure_db()
    with get_session() as session:
        pf = session.query(ParsedFile).filter(ParsedFile.id == file_id).first()
        if pf:
            session.delete(pf)
