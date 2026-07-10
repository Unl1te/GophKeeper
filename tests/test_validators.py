import base64
import pytest

from app.core.validators import is_valid_otp_secret


def test_valid_otp_secret():
    """Test that a valid base32 secret passes validation."""
    secret = base64.b32encode(b"1234567890123456").decode()  # 16 bytes
    assert is_valid_otp_secret(secret.encode()) is True


def test_valid_otp_secret_without_padding():
    """Test that base32 without padding is still valid."""
    secret = "JBSWY3DPEHPK3PXP"  # standard test secret (16 bytes)
    assert is_valid_otp_secret(secret.encode()) is True


def test_invalid_otp_secret_short():
    """Test that a secret shorter than 16 bytes is invalid."""
    secret = base64.b32encode(b"short").decode()
    assert is_valid_otp_secret(secret.encode()) is False


def test_invalid_otp_secret_non_base32():
    """Test that a non-base32 string is invalid."""
    assert is_valid_otp_secret(b"not a valid base32 secret!") is False


def test_empty_otp_secret():
    """Test that empty bytes are invalid."""
    assert is_valid_otp_secret(b"") is False


def test_otp_secret_with_spaces():
    """Test that spaces are invalid (base32 doesn't allow them)."""
    assert is_valid_otp_secret(b"JBSWY3DP EHPK3PXP") is False
