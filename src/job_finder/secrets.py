"""Secure API key storage using the OS keychain + encryption helpers.

Uses the `keyring` library to store secrets in:
- macOS Keychain
- Windows Credential Manager
- Linux Secret Service (GNOME Keyring / KDE Wallet)

Falls back to .env if keyring is unavailable (e.g., headless servers).

For hosted/DB storage, provides Fernet encryption using a key from
the LAUNCHBOARD_SECRET env var or auto-generated and stored in keychain.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

_SERVICE_NAME = "launchboard"


def _keyring():
    """Lazy import keyring to avoid hard dependency."""
    try:
        import keyring as kr
        return kr
    except ImportError:
        return None


def store_secret(key: str, value: str) -> bool:
    """Store a secret in the OS keychain. Returns True on success."""
    if not value:
        delete_secret(key)
        return True
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.set_password(_SERVICE_NAME, key, value)
        return True
    except Exception as exc:
        logger.debug("Keyring store failed for %s: %s", key, exc)
        return False


def get_secret(key: str) -> str:
    """Retrieve a secret from the OS keychain. Returns empty string if not found."""
    kr = _keyring()
    if kr is None:
        return ""
    try:
        value = kr.get_password(_SERVICE_NAME, key)
        return value or ""
    except Exception as exc:
        logger.debug("Keyring read failed for %s: %s", key, exc)
        return ""


def delete_secret(key: str) -> bool:
    """Remove a secret from the OS keychain. Returns True on success."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(_SERVICE_NAME, key)
        return True
    except Exception:
        return False


def is_available() -> bool:
    """Check if keyring is functional on this system."""
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.get_password(_SERVICE_NAME, "__health_check__")
        return True
    except Exception:
        return False


# ── Fernet encryption for DB-stored keys (hosted mode) ──────────────


def _get_fernet_key() -> bytes:
    """Derive a Fernet key from LAUNCHBOARD_SECRET env var.

    Falls back to a machine-specific default (not ideal, but prevents
    plaintext storage even without explicit config).
    """
    secret = os.getenv("LAUNCHBOARD_SECRET", "")
    if not secret:
        # Try keychain
        secret = get_secret("encryption_key")
    if not secret:
        # Generate and store a random key
        secret = base64.urlsafe_b64encode(os.urandom(32)).decode()
        store_secret("encryption_key", secret)
    # Derive a 32-byte key via SHA-256, then base64-encode for Fernet
    raw = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string for safe DB storage. Returns prefixed ciphertext."""
    if not plaintext:
        return ""
    try:
        from cryptography.fernet import Fernet

        f = Fernet(_get_fernet_key())
        return "enc:" + f.encrypt(plaintext.encode()).decode()
    except ImportError:
        logger.warning("cryptography package not installed — storing value without encryption")
        return plaintext
    except Exception as exc:
        logger.error("Encryption failed: %s", exc)
        return plaintext


def decrypt_value(stored: str) -> str:
    """Decrypt a value from DB storage. Handles both encrypted and legacy plaintext."""
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        return stored  # legacy plaintext — return as-is
    try:
        from cryptography.fernet import Fernet

        f = Fernet(_get_fernet_key())
        return f.decrypt(stored[4:].encode()).decode()
    except ImportError:
        logger.warning("cryptography package not installed — cannot decrypt")
        return ""
    except Exception as exc:
        logger.error("Decryption failed: %s", exc)
        return ""
