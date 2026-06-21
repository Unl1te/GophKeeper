"""
Unit tests for JWT functions in app.core.security
"""
import time
import pytest
from datetime import timedelta
from jose import jwt, JWTError
from app.core.config import settings
from app.core.security import create_access_token, decode_token


@pytest.fixture
def sample_data():
    return {"sub": "user123", "role": "admin"}


def test_create_access_token_returns_string(sample_data):
    token = create_access_token(sample_data)
    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3


def test_created_token_contains_provided_claims(sample_data):
    token = create_access_token(sample_data)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["sub"] == "user123"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_token_with_custom_expiry():
    data = {"sub": "1"}
    custom_delta = timedelta(minutes=30)
    token = create_access_token(data, expires_delta=custom_delta)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    from datetime import datetime, timezone

    expected_exp = datetime.now(timezone.utc) + custom_delta
    assert abs((payload["exp"] - expected_exp.timestamp())) < 5


def test_valid_token_decodes_successfully():
    data = {"sub": "test"}
    token = create_access_token(data, expires_delta=timedelta(hours=1))
    payload = decode_token(token)
    assert payload["sub"] == "test"


def test_expired_token_raises_error():
    data = {"sub": "expired"}
    token = create_access_token(data, expires_delta=timedelta(seconds=1))
    time.sleep(2)
    with pytest.raises(JWTError):
        decode_token(token)


def test_future_token_works():
    data = {"sub": "future"}
    token = create_access_token(data, expires_delta=timedelta(days=365))
    payload = decode_token(token)
    assert payload["sub"] == "future"


def test_tampered_payload_rejected(sample_data):
    token = create_access_token(sample_data)
    parts = token.split(".")
    modified_payload = parts[1][::-1]
    fake_token = parts[0] + "." + modified_payload + "." + parts[2]
    with pytest.raises(JWTError):
        decode_token(fake_token)


def test_fake_signature_rejected(sample_data):
    token = create_access_token(sample_data)
    parts = token.split(".")
    fake_token = parts[0] + "." + parts[1] + ".invalidsignaturehere"
    with pytest.raises(JWTError):
        decode_token(fake_token)


def test_token_signed_with_different_key_rejected():
    other_key = "completely-different-secret-key"
    payload = {"sub": "hacker"}
    token = jwt.encode(payload, other_key, algorithm=settings.ALGORITHM)
    with pytest.raises(JWTError):
        decode_token(token)


def test_decode_empty_string_raises_error():
    with pytest.raises(JWTError):
        decode_token("")


def test_decode_garbage_string_raises_error():
    with pytest.raises(JWTError):
        decode_token("this.is.not.a.valid.jwt")


def test_decode_none_raises_error():
    with pytest.raises((JWTError, AttributeError, TypeError)):
        decode_token(None)


def test_decode_corrupted_base64_raises_error():
    with pytest.raises(JWTError):
        decode_token("header.!!!!@@@@@.signature")


def test_decode_missing_parts_raises_error():
    with pytest.raises(JWTError):
        decode_token("only.two.parts")


def test_decode_extra_parts_raises_error():
    with pytest.raises(JWTError):
        decode_token("one.two.three.four.five")

def test_decode_with_wrong_algorithm():
    payload = {"sub": "test"}                                 
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS512")
    with pytest.raises(JWTError):
        decode_token(token)
