"""
Post-parse normalization helpers: dates, amounts, NPI formatting.
"""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value: str, fmt: str = "%Y%m%d") -> date | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    try:
        return datetime.strptime(value, fmt).date()
    except ValueError:
        pass
    # Try alternate formats
    for f in ("%Y%m%d", "%y%m%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, f).date()
        except ValueError:
            continue
    return None


def parse_amount(value: str) -> float | None:
    if not value or not value.strip():
        return None
    try:
        return float(Decimal(value.strip()))
    except (InvalidOperation, ValueError):
        return None


def clean_npi(value: str) -> str:
    if not value:
        return ""
    return value.strip().lstrip("0" if len(value.strip()) > 10 else "")


def safe_get(elements: list[str], index: int, default: str = "") -> str:
    try:
        return elements[index].strip()
    except IndexError:
        return default
