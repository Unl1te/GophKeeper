import pytest
from app.core.validators import is_valid_otp_secret

VALID_LONG_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # 32 chars → 20 bytes


def test_valid_otp_secret():
    assert is_valid_otp_secret(VALID_LONG_SECRET.encode()) is True


def test_valid_otp_secret_without_padding():
    assert is_valid_otp_secret(VALID_LONG_SECRET.encode()) is True


def test_invalid_otp_secret_short():
    short = "JBSWY3DP"  # 8 chars → 5 bytes
    assert is_valid_otp_secret(short.encode()) is False


def test_invalid_otp_secret_non_base32():
    assert is_valid_otp_secret(b"not a valid base32 secret!") is False


def test_empty_otp_secret():
    assert is_valid_otp_secret(b"") is False


def test_otp_secret_with_spaces():
    assert is_valid_otp_secret(b"JBSWY3DP EHPK3PXP") is False
