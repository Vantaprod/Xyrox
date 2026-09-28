"""
Xyrox — Password Hashing (Phase 3, File 2, fixed)

Uses the `bcrypt` library directly. Passlib has been removed because
it is unmaintained (last release 2020) and incompatible with
bcrypt >= 4.1.

Rules:
- Never store plaintext passwords. Ever.
- Never log them. Ever.
- Never return them in API responses. Ever.
- Passwords shorter than 8 bytes or longer than 72 bytes are rejected
  explicitly. bcrypt has a hard 72-byte limit. We surface that
  clearly rather than silently truncating (Master Command §18).
- Cost factor is 12. This is slow enough to be safe, fast enough to
  be usable (roughly 250 ms per hash on the target hardware).
"""

import bcrypt

from app.backend.tools.base import ToolValidationError


BCRYPT_ROUNDS = 12
MIN_PASSWORD_BYTES = 8
MAX_PASSWORD_BYTES = 72  # bcrypt's hard limit


def hash_password(plain: str) -> str:
    """
    Hash a plaintext password with bcrypt. Returns the hash as a string.

    Raises ToolValidationError if the password is invalid (wrong type,
    too short, too long).
    """
    if not isinstance(plain, str):
        raise ToolValidationError("Password must be a string.")

    encoded = plain.encode("utf-8")

    if len(encoded) < MIN_PASSWORD_BYTES:
        raise ToolValidationError(
            f"Password must be at least {MIN_PASSWORD_BYTES} bytes "
            f"(UTF-8) long."
        )
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ToolValidationError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            f"(UTF-8) long."
        )

    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(encoded, salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Return True if the plaintext matches the hash. Never raises.
    """
    if not isinstance(plain, str) or not isinstance(hashed, str):
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False