"""Cross-file aggregation: query parsed records from SQLite for analytics."""
from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from storage.database import get_session

CLP_STATUS_MAP = {
    "1": "Processed as Primary", "2": "Processed as Other",
    "3": "Processed as Secondary", "4": "Denied",
    "19": "Forwarded (Primary)", "20": "Forwarded (Secondary)",
    "22": "Reversal",
}


def get_claims_df(
    file_ids: list[int] | None = None,
    dos_from: str | None = None,
    dos_to: str | None = None,
    payer_id: str | None = None,
) -> pd.DataFrame:
    """Return 837P claims as a DataFrame with optional filters."""
    conditions = ["1=1"]
    params: dict = {}
    if file_ids:
        placeholders = ",".join(f":fid{i}" for i, _ in enumerate(file_ids))
        conditions.append(f"file_id IN ({placeholders})")
        for i, fid in enumerate(file_ids):
            params[f"fid{i}"] = fid
    if dos_from:
        conditions.append("dos_from >= :dos_from")
        params["dos_from"] = dos_from
    if dos_to:
        conditions.append("dos_from <= :dos_to")
        params["dos_to"] = dos_to
    if payer_id:
        conditions.append("payer_id = :payer_id")
        params["payer_id"] = payer_id
    where = " AND ".join(conditions)
    sql = text(f"SELECT * FROM claims_837 WHERE {where}")
    with get_session() as s:
        return pd.read_sql(sql, s.bind, params=params)


def get_service_lines_df(claim_ids: list[str] | None = None) -> pd.DataFrame:
    conditions = ["1=1"]
    params: dict = {}
    if claim_ids:
        placeholders = ",".join(f":cid{i}" for i, _ in enumerate(claim_ids))
        conditions.append(f"claim_id IN ({placeholders})")
        for i, cid in enumerate(claim_ids):
            params[f"cid{i}"] = cid
    sql = text(f"SELECT * FROM service_lines_837 WHERE {' AND '.join(conditions)}")
    with get_session() as s:
        return pd.read_sql(sql, s.bind, params=params)


def get_payments_df(
    file_ids: list[int] | None = None,
    status_codes: list[str] | None = None,
) -> pd.DataFrame:
    conditions = ["1=1"]
    params: dict = {}
    if file_ids:
        placeholders = ",".join(f":fid{i}" for i, _ in enumerate(file_ids))
        conditions.append(f"file_id IN ({placeholders})")
        for i, fid in enumerate(file_ids):
            params[f"fid{i}"] = fid
    if status_codes:
        placeholders = ",".join(f":sc{i}" for i, _ in enumerate(status_codes))
        conditions.append(f"status_code IN ({placeholders})")
        for i, sc in enumerate(status_codes):
            params[f"sc{i}"] = sc
    sql = text(f"SELECT * FROM claim_payments_835 WHERE {' AND '.join(conditions)}")
    with get_session() as s:
        return pd.read_sql(sql, s.bind, params=params)


def get_adjustments_df(file_ids: list[int] | None = None) -> pd.DataFrame:
    params: dict = {}
    conditions = ["1=1"]
    if file_ids:
        placeholders = ",".join(f":fid{i}" for i, _ in enumerate(file_ids))
        conditions.append(f"file_id IN ({placeholders})")
        for i, fid in enumerate(file_ids):
            params[f"fid{i}"] = fid
    sql = text(f"SELECT * FROM adjustments_835 WHERE {' AND '.join(conditions)}")
    with get_session() as s:
        return pd.read_sql(sql, s.bind, params=params)


def get_files_df() -> pd.DataFrame:
    sql = text("SELECT * FROM files ORDER BY upload_ts DESC")
    with get_session() as s:
        return pd.read_sql(sql, s.bind)
