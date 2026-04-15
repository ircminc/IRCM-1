"""
Structured audit logger for HIPAA-conscious event tracking.

Records the following event types:
  FILE_UPLOAD    — an EDI file was received
  FILE_PARSE     — parsing completed (success or failure)
  FILE_EXPORT    — a file was exported (Excel/PDF)
  FILE_DELETE    — a record was deleted from the database
  RATE_LOOKUP    — a CMS rate lookup was performed
  SESSION_START  — a new browser session started
  SESSION_END    — session cleaned up (files purged)
  PHI_MASKED     — PHI masking was applied to an output

Each event is written as a JSON line to the audit log file and is also
emitted via the 'audit' Python logger so it flows through the central
logging setup (see app/utils/logging_config.py).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("audit")


# ── Event constants ────────────────────────────────────────────────────────────

class AuditEvent:
    FILE_UPLOAD    = "FILE_UPLOAD"
    FILE_PARSE     = "FILE_PARSE"
    FILE_EXPORT    = "FILE_EXPORT"
    FILE_DELETE    = "FILE_DELETE"
    RATE_LOOKUP    = "RATE_LOOKUP"
    SESSION_START  = "SESSION_START"
    SESSION_END    = "SESSION_END"
    PHI_MASKED     = "PHI_MASKED"
    HIPAA_MODE_ON  = "HIPAA_MODE_ENABLED"
    HIPAA_MODE_OFF = "HIPAA_MODE_DISABLED"


# ── Core logging function ──────────────────────────────────────────────────────

def log_event(
    event_type: str,
    details: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> None:
    """
    Emit a structured audit event.

    Args:
        event_type:  One of the AuditEvent constants.
        details:     Free-form dict with event-specific metadata.
                     Do NOT include raw PHI here.
        session_id:  Browser session identifier (from Streamlit session state).
    """
    record = {
        "event":      event_type,
        "ts":         datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "unknown",
        "event_id":   str(uuid.uuid4()),
    }
    if details:
        # Sanitize: drop any keys that look like PHI
        safe_details = {
            k: v for k, v in details.items()
            if k.lower() not in _PHI_FIELD_NAMES
        }
        record["details"] = safe_details

    logger.info(json.dumps(record), extra={"audit_record": record})


# ── PHI field name deny-list (prevent accidental PHI in audit logs) ────────────

_PHI_FIELD_NAMES = {
    "patient_name", "patient_first", "patient_last", "patient_dob",
    "subscriber_name", "member_name", "dob", "date_of_birth",
    "ssn", "social_security", "address", "street", "phone", "email",
    "member_id", "subscriber_id",   # IDs could be considered PHI in some contexts
}


# ── Convenience wrappers ───────────────────────────────────────────────────────

def log_upload(filename: str, file_size_bytes: int, session_id: str | None = None) -> None:
    log_event(AuditEvent.FILE_UPLOAD, {
        "filename":        filename,
        "file_size_bytes": file_size_bytes,
    }, session_id)


def log_parse(filename: str, tx_type: str, success: bool,
              record_count: int = 0, duration_ms: int = 0,
              session_id: str | None = None) -> None:
    log_event(AuditEvent.FILE_PARSE, {
        "filename":     filename,
        "tx_type":      tx_type,
        "success":      success,
        "record_count": record_count,
        "duration_ms":  duration_ms,
    }, session_id)


def log_export(filename: str, tx_type: str, format: str,
               session_id: str | None = None) -> None:
    log_event(AuditEvent.FILE_EXPORT, {
        "filename": filename,
        "tx_type":  tx_type,
        "format":   format,
    }, session_id)


def log_delete(file_id: int, tx_type: str, session_id: str | None = None) -> None:
    log_event(AuditEvent.FILE_DELETE, {
        "file_id": file_id,
        "tx_type": tx_type,
    }, session_id)


def log_rate_lookup(cpt: str, session_id: str | None = None) -> None:
    log_event(AuditEvent.RATE_LOOKUP, {"cpt": cpt}, session_id)


def log_phi_masked(context: str, field_count: int, session_id: str | None = None) -> None:
    log_event(AuditEvent.PHI_MASKED, {
        "context":     context,
        "field_count": field_count,
    }, session_id)
