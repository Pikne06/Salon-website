import hashlib
import secrets
import string
from typing import Tuple

from werkzeug.security import generate_password_hash, check_password_hash

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Return a secure PBKDF2-based hash for the provided password.

    Uses Werkzeug's `generate_password_hash` to produce a salted, iterated
    PBKDF2 hash (`pbkdf2:sha256`) which is suitable for user passwords.
    """
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)


def verify_password(password: str, hashed: str) -> bool:
    """Check if the provided password matches the stored hash.

    This expects modern hashed values produced by `hash_password`.
    """
    return check_password_hash(hashed, password)


def is_legacy_hash(hashed: str) -> bool:
    """Detect old SHA-256 hex digests (64 hex chars)."""
    if not isinstance(hashed, str):
        return False
    if len(hashed) != 64:
        return False
    try:
        int(hashed, 16)
        return True
    except ValueError:
        return False


def has_special_char(password: str) -> bool:
    return any(char in string.punctuation for char in password)


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def validate_password(password: str) -> Tuple[bool, str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, "Password must be at least 8 characters long."
    if not any(char.isdigit() for char in password):
        return False, "Password must contain at least one digit."
    if not any(char.isupper() for char in password):
        return False, "Password must contain at least one uppercase letter."
    if not has_special_char(password):
        return False, "Password must contain at least one special character."
    return True, ""