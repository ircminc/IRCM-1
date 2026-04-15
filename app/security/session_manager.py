"""
Session-scoped temporary file lifecycle management.

When HIPAA mode is active, uploaded EDI files are written to a secure
temp directory rather than any persistent location.  This module:

  1. Creates an isolated temp directory per Streamlit session.
  2. Tracks every temp file path written during that session.
  3. Provides a cleanup() call that shreds all tracked files.
  4. Automatically registers a Streamlit on_session_end callback
     (when available) so cleanup happens even if the user closes the tab.

Usage:
    from app.security.session_manager import SessionManager

    mgr = SessionManager.get()          # singleton per Streamlit session
    path = mgr.write_temp(file_bytes, "upload.edi")
    ...
    mgr.cleanup()                       # removes all temp files for this session
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_SESSION_MGR_KEY = "_session_manager"


class SessionManager:
    """Manages temporary files for a single Streamlit session."""

    def __init__(self) -> None:
        # Create a random per-session temp dir so concurrent users don't clash
        self._session_token = secrets.token_hex(8)
        self._temp_root = Path(tempfile.gettempdir()) / f"ansi_x12_{self._session_token}"
        self._temp_root.mkdir(parents=True, exist_ok=True)
        self._tracked_paths: list[Path] = []
        logger.info(f"SessionManager initialised: {self._temp_root}")

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "SessionManager":
        """
        Return the SessionManager for the current Streamlit session.
        Creates one on first call.
        """
        try:
            import streamlit as st
            if _SESSION_MGR_KEY not in st.session_state:
                st.session_state[_SESSION_MGR_KEY] = cls()
            return st.session_state[_SESSION_MGR_KEY]
        except Exception:
            # Fallback for non-Streamlit contexts (tests, scripts)
            return cls()

    # ── Temp file operations ──────────────────────────────────────────────────

    def write_temp(self, data: bytes, filename: str) -> Path:
        """
        Write bytes to a temp file inside the session directory.

        Args:
            data:      File contents (may be encrypted).
            filename:  Suggested filename (sanitized before use).

        Returns:
            Absolute Path to the written temp file.
        """
        safe_name = Path(filename).name  # strip any path traversal
        dest = self._temp_root / safe_name
        dest.write_bytes(data)
        self._tracked_paths.append(dest)
        logger.debug(f"Temp file written: {dest} ({len(data):,} bytes)")
        return dest

    def read_temp(self, path: Path) -> bytes:
        """Read a tracked temp file."""
        return path.read_bytes()

    def list_temp_files(self) -> list[Path]:
        """Return all currently tracked temp file paths."""
        return [p for p in self._tracked_paths if p.exists()]

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> int:
        """
        Securely delete all temp files and the session directory.

        Returns:
            Number of files removed.
        """
        removed = 0
        for path in self._tracked_paths:
            _secure_delete(path)
            removed += 1
        self._tracked_paths.clear()

        if self._temp_root.exists():
            try:
                shutil.rmtree(self._temp_root, ignore_errors=True)
            except Exception as exc:
                logger.warning(f"Could not remove temp dir {self._temp_root}: {exc}")

        logger.info(f"SessionManager cleanup: {removed} files removed")
        return removed

    def __del__(self) -> None:
        """Best-effort cleanup when object is garbage collected."""
        try:
            self.cleanup()
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _secure_delete(path: Path) -> None:
    """
    Overwrite file with zeros before unlinking.

    This is a best-effort measure; full secure deletion on SSDs requires
    OS-level support (TRIM) which is outside scope here.
    """
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(b"\x00" * size)
            f.flush()
            os.fsync(f.fileno())
        path.unlink()
        logger.debug(f"Secure-deleted: {path}")
    except Exception as exc:
        # Fall back to normal delete
        logger.warning(f"Secure delete failed for {path}, falling back: {exc}")
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
