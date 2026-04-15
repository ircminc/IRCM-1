"""
Lightweight symmetric file encryption for temporary EDI file storage.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the cryptography library.
A per-session key is generated and stored only in Streamlit's session_state —
it is NEVER written to disk.  When the session ends the key is lost and the
encrypted bytes become unreadable.

Usage:
    from app.security.encryption import encrypt_bytes, decrypt_bytes, get_session_key

    key  = get_session_key()          # lazily generated, stored in session_state
    blob = encrypt_bytes(raw, key)    # returns ciphertext bytes
    raw  = decrypt_bytes(blob, key)   # raises InvalidToken if tampered

When HIPAA mode is off the encrypt/decrypt functions are no-ops so the rest
of the codebase can call them unconditionally.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# ── Optional dependency guard ─────────────────────────────────────────────────
try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    logger.warning(
        "cryptography library not installed — file encryption disabled. "
        "Install with: pip install cryptography"
    )


# ── Key management ─────────────────────────────────────────────────────────────

def generate_key() -> bytes:
    """Generate a new Fernet key (32 bytes URL-safe base64-encoded)."""
    if not _CRYPTO_AVAILABLE:
        return b""
    return Fernet.generate_key()


def get_session_key() -> bytes:
    """
    Return the encryption key for the current Streamlit session.
    Creates a new key if one does not yet exist in session_state.
    Falls back to a transient in-memory key if Streamlit is not running.
    """
    if not _CRYPTO_AVAILABLE:
        return b""

    try:
        import streamlit as st
        if "_enc_key" not in st.session_state:
            st.session_state["_enc_key"] = generate_key()
        return st.session_state["_enc_key"]
    except Exception:
        # Not running in Streamlit context (e.g., tests)
        return generate_key()


# ── Encrypt / Decrypt ─────────────────────────────────────────────────────────

def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """
    Encrypt raw bytes with Fernet.

    Returns the original bytes unchanged if:
    - cryptography is not installed, or
    - key is empty (HIPAA mode disabled)
    """
    if not _CRYPTO_AVAILABLE or not key:
        return data
    try:
        return Fernet(key).encrypt(data)
    except Exception as exc:
        logger.error(f"Encryption failed: {exc}")
        return data          # fail open — data is still usable


def decrypt_bytes(data: bytes, key: bytes) -> bytes:
    """
    Decrypt Fernet-encrypted bytes.

    Returns the original bytes unchanged if:
    - cryptography is not installed, or
    - key is empty (HIPAA mode disabled)

    Raises:
        InvalidToken: if the data was tampered with or the wrong key is used.
    """
    if not _CRYPTO_AVAILABLE or not key:
        return data
    return Fernet(key).decrypt(data)   # intentionally propagate InvalidToken


def is_available() -> bool:
    """Return True if the cryptography library is installed."""
    return _CRYPTO_AVAILABLE
