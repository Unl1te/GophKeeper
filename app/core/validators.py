import base64
from typing import Optional


def is_valid_otp_secret(content: bytes) -> bool:
    """
    Validate that the given bytes represent a valid base32-encoded OTP secret.
    Returns True if the content can be decoded as base32 and has a valid length.
    """
    if not content:
        return False
    try:
        # Try to decode as base32 (ignoring padding)
        decoded = base64.b32decode(content, casefold=True)
        # Secret should be at least 16 bytes (128 bits) for security
        return len(decoded) >= 16
    except (base64.binascii.Error, ValueError):
        return False
