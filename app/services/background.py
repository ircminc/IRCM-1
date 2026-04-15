"""
Background Processing Service (Phase 5 — Performance)

For files larger than the configured threshold (default 10 MB), parsing is
offloaded to a background thread so the Streamlit UI remains responsive.

The caller receives a ParseFuture object and can poll .done() or call
.result(timeout=N) to block until the parse completes.

Streamlit integration pattern (in a page):

    future = submit_parse(file_bytes, filename, session_id)
    progress = st.progress(0, text="Parsing large file…")
    while not future.done():
        time.sleep(0.5)
        progress.progress(50)   # indeterminate — update as available
    progress.progress(100)
    result = future.result()
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Callable

from app.services.parse_service import ParseResult, parse_edi

logger = logging.getLogger(__name__)

# Module-level thread pool — shared across all sessions
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="edi_parse",
)


class ParseFuture:
    """Thin wrapper around concurrent.futures.Future for EDI parse jobs."""

    def __init__(self, future: concurrent.futures.Future, submitted_at: float) -> None:
        self._future = future
        self._submitted_at = submitted_at

    def done(self) -> bool:
        """Return True if parsing has completed (success or failure)."""
        return self._future.done()

    def elapsed_ms(self) -> int:
        """Milliseconds since the job was submitted."""
        return int((time.monotonic() - self._submitted_at) * 1000)

    def result(self, timeout: float | None = 300.0) -> ParseResult:
        """
        Block until the parse completes and return the ParseResult.

        Args:
            timeout: Seconds to wait before raising TimeoutError (default 5 min).
        """
        return self._future.result(timeout=timeout)

    def cancel(self) -> bool:
        """Attempt to cancel a queued (not yet running) job."""
        return self._future.cancel()


def submit_parse(
    file_bytes: bytes,
    filename: str,
    session_id: str | None = None,
    on_complete: Callable[[ParseResult], None] | None = None,
) -> ParseFuture:
    """
    Submit an EDI file for background parsing.

    Args:
        file_bytes:   Raw EDI file contents.
        filename:     Original filename for logging and audit.
        session_id:   Streamlit session ID for audit logging.
        on_complete:  Optional callback invoked with ParseResult when done.

    Returns:
        ParseFuture — call .done() to check status, .result() to retrieve.
    """
    def _wrapped():
        res = parse_edi(file_bytes, filename, session_id)
        if on_complete:
            try:
                on_complete(res)
            except Exception as exc:
                logger.warning(f"on_complete callback raised: {exc}")
        return res

    submitted_at = time.monotonic()
    future = _EXECUTOR.submit(_wrapped)
    logger.info(f"Background parse submitted: {filename!r} ({len(file_bytes):,} bytes)")
    return ParseFuture(future, submitted_at)


def should_use_background(file_size_bytes: int) -> bool:
    """
    Return True if the file is large enough to warrant background processing.
    Reads threshold from settings (default 10 MB).
    """
    try:
        from config import settings
        threshold = settings.background_processing_threshold_mb * 1024 * 1024
    except Exception:
        threshold = 10 * 1024 * 1024   # 10 MB fallback
    return file_size_bytes >= threshold
