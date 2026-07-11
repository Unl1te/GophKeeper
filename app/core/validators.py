import base64
from typing import Optional


def _add_padding(data: bytes) -> bytes:
    """Add base32 padding ('=') so the length is a multiple of 8."""
    missing = 8 - (len(data) % 8)
    if missing != 8:
        data += b"=" * missing
    return data


def is_valid_otp_secret(content: bytes) -> bool:
    """
    Validate that the given bytes represent a valid base32-encoded OTP secret.
    Returns True if the content can be decoded as base32 (with padding auto-added)
    and the decoded length is at least 16 bytes.
    """
    if not content:
        return False
    try:
        padded = _add_padding(content)
        decoded = base64.b32decode(padded, casefold=True)
        return len(decoded) >= 16
    except Exception:
        return False
