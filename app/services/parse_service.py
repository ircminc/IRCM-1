"""
Parse Service — orchestration layer over core/parser.

Responsibilities:
  - Accept raw file bytes and a filename
  - Detect transaction type before full parse
  - Invoke the appropriate parser
  - Measure parse duration
  - Emit audit log events
  - Return a typed ParseResult (success or failure) instead of raw dicts

This layer keeps the Streamlit pages thin: they call parse_edi() and
receive a clean result object regardless of which TX type was uploaded.

Usage:
    from app.services.parse_service import parse_edi, ParseResult

    result = parse_edi(file_bytes, "claim_batch.edi")
    if result.success:
        print(result.tx_type, result.record_count)
    else:
        print(result.error)
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    """Encapsulates the outcome of parsing a single EDI file."""

    filename: str
    tx_type: str          # 837P | 835 | 270 | 271 | 276 | 277 | 834 | 820 | UNKNOWN
    success: bool
    data: dict[str, Any] = field(default_factory=dict)   # raw parsed payload
    record_count: int = 0
    duration_ms: int = 0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.success:
            return (
                f"{self.tx_type} — {self.record_count:,} records "
                f"parsed in {self.duration_ms} ms"
            )
        return f"Parse failed: {self.error}"


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_edi(
    file_bytes: bytes,
    filename: str,
    session_id: str | None = None,
) -> ParseResult:
    """
    Parse raw EDI bytes and return a ParseResult.

    Args:
        file_bytes:  Raw contents of the uploaded EDI file.
        filename:    Original filename (used for logging only).
        session_id:  Streamlit session ID for audit logging.

    Returns:
        ParseResult with .success, .tx_type, .data, .record_count, .duration_ms
    """
    from core.parser.base_parser import parse_edi_file, detect_tx_type
    from app.security.audit_logger import log_parse

    t0 = time.monotonic()

    # ── Step 1: detect TX type cheaply before full parse ─────────────────────
    try:
        source = io.BytesIO(file_bytes)
        tx_type = detect_tx_type(source)
    except Exception as exc:
        duration = int((time.monotonic() - t0) * 1000)
        log_parse(filename, "UNKNOWN", False, 0, duration, session_id)
        return ParseResult(
            filename=filename,
            tx_type="UNKNOWN",
            success=False,
            error=f"Could not detect transaction type: {exc}",
            duration_ms=duration,
        )

    # ── Step 2: full parse ────────────────────────────────────────────────────
    try:
        source = io.BytesIO(file_bytes)
        parsed = parse_edi_file(source)
        duration = int((time.monotonic() - t0) * 1000)

        record_count = _count_records(parsed, tx_type)
        warnings     = _validate_result(parsed, tx_type)

        log_parse(filename, tx_type, True, record_count, duration, session_id)
        logger.info(
            f"Parsed {filename!r}: tx={tx_type}, records={record_count}, "
            f"duration={duration}ms, warnings={len(warnings)}"
        )

        return ParseResult(
            filename=filename,
            tx_type=tx_type,
            success=True,
            data=parsed.get("data", {}),   # inner payload only: {"claims":[]} / {"claim_payments":[]} etc.
            record_count=record_count,
            duration_ms=duration,
            warnings=warnings,
        )

    except Exception as exc:
        duration = int((time.monotonic() - t0) * 1000)
        log_parse(filename, tx_type, False, 0, duration, session_id)
        logger.error(f"Parse failed for {filename!r}: {exc}", exc_info=True)
        return ParseResult(
            filename=filename,
            tx_type=tx_type,
            success=False,
            error=str(exc),
            duration_ms=duration,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_records(parsed: dict, tx_type: str) -> int:
    """
    Return a meaningful record count for each transaction type.
    `parsed` here is the full dict from parse_edi_file (keys: tx_type, data, envelope, …).
    We reach into parsed["data"] to count the domain objects.
    """
    inner = parsed.get("data", {})
    counts = {
        "837P": lambda d: len(d.get("claims", [])),
        "835":  lambda d: len(d.get("claim_payments", [])),
        "270":  lambda d: len(d.get("inquiries", [])),
        "271":  lambda d: len(d.get("responses", [])),
        "276":  lambda d: len(d.get("inquiries", [])),
        "277":  lambda d: len(d.get("responses", [])),
        "834":  lambda d: len(d.get("members", [])),
        "820":  lambda d: len(d.get("remittances", [])),
    }
    fn = counts.get(tx_type)
    try:
        return fn(inner) if fn else 0
    except Exception:
        return 0


def _validate_result(parsed: dict, tx_type: str) -> list[str]:
    """
    Run lightweight post-parse validation checks.
    Returns list of human-readable warning strings (empty = all OK).
    """
    warnings: list[str] = []

    # Envelope checks
    env = parsed.get("envelope")
    if env and hasattr(env, "version") and env.version:
        if not env.version.startswith("005"):
            warnings.append(
                f"ISA version {env.version!r} — expected HIPAA 5010 (005xxx)"
            )

    # 837P specific
    if tx_type == "837P":
        claims = parsed.get("data", {}).get("claims", [])
        if not claims:
            warnings.append("No claims found in 837P transaction set")

    # 835 specific
    if tx_type == "835":
        header = parsed.get("data", {}).get("header")
        if header and getattr(header, "total_payment", None) is None:
            warnings.append("835 BPR segment (payment total) not found")

    return warnings


# ── Streaming / background variant ────────────────────────────────────────────

def parse_edi_async(
    file_bytes: bytes,
    filename: str,
    callback: Any = None,
    session_id: str | None = None,
) -> "ParseFuture":
    """
    Submit parsing to a background thread and return a future-like object.
    Use this for files > ~10 MB to keep the Streamlit UI responsive.

    Args:
        file_bytes:  Raw EDI bytes.
        filename:    Original filename.
        callback:    Optional callable(ParseResult) invoked on completion.
        session_id:  For audit logging.

    Returns:
        ParseFuture with .done() and .result() methods.
    """
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(parse_edi, file_bytes, filename, session_id)
    executor.shutdown(wait=False)

    class ParseFuture:
        def done(self) -> bool:
            return future.done()
        def result(self, timeout: float | None = None) -> ParseResult:
            res = future.result(timeout=timeout)
            if callback:
                try:
                    callback(res)
                except Exception:
                    pass
            return res

    return ParseFuture()
