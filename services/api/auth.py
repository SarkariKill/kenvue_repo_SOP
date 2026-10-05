import hashlib
import os
import secrets
from typing import Optional, Tuple

# =====================================================================
# USER AUTHENTICATION & PASSWORD HASHING
# Simple, robust SHA256+salt hashing with zero external dependencies.
# =====================================================================

def hash_password(password: str) -> str:
    """Hash password with a unique random salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:hash."""
    try:
        salt, expected_hash = stored_hash.split(":", 1)
        actual_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(expected_hash, actual_hash)
    except Exception:
        return False
