"""
PHI (Protected Health Information) masking for exported outputs.

When HIPAA mode is active or the user toggles "Mask PHI" in the UI,
this module replaces identifiable fields in DataFrames and dictionaries
with anonymized placeholders before the data is displayed or exported.

Masking strategy:
  Names     →  First letter + asterisks (e.g. "John Smith" → "J*** S***")
  DOB       →  Year retained, month/day masked  ("1985-07-22" → "1985-**-**")
  IDs/NPIs  →  Last 4 digits retained, rest replaced  ("1234567890" → "******7890")
  Addresses →  Replaced with "[MASKED]"
  Phone     →  Replaced with "***-***-XXXX"

Usage:
    from app.security.phi_masker import mask_dataframe, mask_dict, PHI_COLS_837P

    masked_df = mask_dataframe(df, PHI_COLS_837P)
"""
from __future__ import annotations

import re
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ── PHI column registries ──────────────────────────────────────────────────────
# Maps column name → masking strategy name

PHI_COLS_837P: dict[str, str] = {
    "patient_last":       "name_part",
    "patient_first":      "name_part",
    "patient_dob":        "dob",
    "subscriber_id":      "id_last4",
    "subscriber_name":    "name",
    "billing_provider_npi": "npi",
    "rendering_provider_npi": "npi",
    "claim_id":           "id_last4",
}

PHI_COLS_835: dict[str, str] = {
    "patient_name":       "name",
    "clp_id":             "id_last4",
    "payer_claim_number": "id_last4",
}

PHI_COLS_270_271: dict[str, str] = {
    "subscriber_name":    "name",
    "subscriber_id":      "id_last4",
    "dob":                "dob",
    "group_number":       "id_last4",
}


# ── Individual masking functions ───────────────────────────────────────────────

def mask_name(value: str) -> str:
    """'John Smith' → 'J*** S***'"""
    if not value or not isinstance(value, str):
        return value
    parts = value.strip().split()
    return " ".join(
        (p[0] + "***") if len(p) > 1 else p
        for p in parts
    )


def mask_name_part(value: str) -> str:
    """Single name part: 'Smith' → 'S***'"""
    if not value or not isinstance(value, str):
        return value
    v = value.strip()
    return (v[0] + "***") if len(v) > 1 else v


def mask_dob(value: str) -> str:
    """
    Retain birth year only: '1985-07-22' → '1985-**-**'
    Handles YYYYMMDD and YYYY-MM-DD formats.
    """
    if not value or not isinstance(value, str):
        return value
    v = value.strip()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        return v[:4] + "-**-**"
    # YYYYMMDD
    if re.match(r"^\d{8}$", v):
        return v[:4] + "****"
    return "****"


def mask_id(value: str, keep_last: int = 4) -> str:
    """'1234567890' → '******7890'"""
    if not value or not isinstance(value, str):
        return value
    v = value.strip()
    if len(v) <= keep_last:
        return "*" * len(v)
    return "*" * (len(v) - keep_last) + v[-keep_last:]


def mask_npi(value: str) -> str:
    """NPI: keep last 4 → 'NPI-****7890'"""
    if not value or not isinstance(value, str):
        return value
    v = value.strip()
    return "NPI-" + ("*" * max(0, len(v) - 4)) + v[-4:]


def mask_address(value: str) -> str:
    return "[MASKED]"


def mask_phone(value: str) -> str:
    return "***-***-XXXX"


# ── Strategy dispatch ──────────────────────────────────────────────────────────

_STRATEGY_MAP: dict[str, Any] = {
    "name":       mask_name,
    "name_part":  mask_name_part,
    "dob":        mask_dob,
    "id_last4":   mask_id,
    "npi":        mask_npi,
    "address":    mask_address,
    "phone":      mask_phone,
}


def _apply_strategy(value: Any, strategy: str) -> Any:
    if pd.isna(value) if hasattr(pd, "isna") else value is None:
        return value
    fn = _STRATEGY_MAP.get(strategy)
    if fn is None:
        logger.warning(f"Unknown masking strategy: {strategy!r}")
        return "[MASKED]"
    return fn(str(value))


# ── DataFrame masker ───────────────────────────────────────────────────────────

def mask_dataframe(
    df: pd.DataFrame,
    phi_columns: dict[str, str],
) -> pd.DataFrame:
    """
    Return a copy of df with PHI columns masked.

    Args:
        df:          Input DataFrame.
        phi_columns: Mapping of column_name → masking_strategy.

    Returns:
        New DataFrame with matching columns replaced.
    """
    masked = df.copy()
    count = 0
    for col, strategy in phi_columns.items():
        if col in masked.columns:
            masked[col] = masked[col].apply(lambda v: _apply_strategy(v, strategy))
            count += masked[col].notna().sum()
    logger.debug(f"Masked {count} PHI values across {len(phi_columns)} columns")
    return masked


# ── Dict masker (for single-record outputs) ────────────────────────────────────

def mask_dict(record: dict, phi_columns: dict[str, str]) -> dict:
    """
    Return a copy of the dict with PHI fields masked.
    """
    out = dict(record)
    for key, strategy in phi_columns.items():
        if key in out:
            out[key] = _apply_strategy(out[key], strategy)
    return out


# ── Convenience: auto-detect and mask a DataFrame by TX type ─────────────────

_TX_PHI_MAP: dict[str, dict[str, str]] = {
    "837P": PHI_COLS_837P,
    "835":  PHI_COLS_835,
    "270":  PHI_COLS_270_271,
    "271":  PHI_COLS_270_271,
}

def auto_mask(df: pd.DataFrame, tx_type: str) -> pd.DataFrame:
    """Apply standard PHI masking for the given transaction type."""
    phi_cols = _TX_PHI_MAP.get(tx_type.upper(), {})
    if not phi_cols:
        return df
    return mask_dataframe(df, phi_cols)
