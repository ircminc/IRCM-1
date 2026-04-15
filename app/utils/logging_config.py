"""
Centralized logging configuration for the ANSI X12 Billing Converter.

Sets up:
- Structured JSON log formatter for production/cloud deployments
- Human-readable formatter for local development
- Separate audit log handler (always JSON)
- Root logger configuration used across all modules
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── JSON formatter for structured logging ────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects for log aggregation tools."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Attach any extra fields passed via extra={} in logging calls
        for key, val in record.__dict__.items():
            if key not in (
                "args", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message",
                "module", "msecs", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "taskName",
                "thread", "threadName",
            ):
                try:
                    json.dumps(val)          # only include JSON-serialisable extras
                    payload[key] = val
                except (TypeError, ValueError):
                    payload[key] = str(val)
        return json.dumps(payload, ensure_ascii=False)


# ── Setup function ────────────────────────────────────────────────────────────

def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    audit_log_path: Path | None = None,
) -> None:
    """
    Configure the root logger.

    Args:
        level:           Log level string (DEBUG / INFO / WARNING / ERROR).
        json_output:     True → JSON formatter; False → human-readable.
        audit_log_path:  If given, attach a dedicated FileHandler for audit events.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any handlers added before this call (e.g. Streamlit's own handler)
    for h in root.handlers[:]:
        root.removeHandler(h)

    # ── Console handler ───────────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    if json_output:
        console.setFormatter(JSONFormatter())
    else:
        console.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s  %(levelname)-8s  %(name)-30s  %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(console)

    # ── Audit file handler (always JSON) ──────────────────────────────────────
    if audit_log_path:
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(audit_log_path, encoding="utf-8")
        fh.setFormatter(JSONFormatter())
        fh.setLevel(logging.INFO)
        # Only route records from the dedicated audit logger
        fh.addFilter(lambda r: r.name.startswith("audit"))
        root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
