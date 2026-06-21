import pytest
import crypto_interface as crypto


def test_hash_password_returns_str():
    result = crypto.hash_password("test123")
    assert isinstance(result, str)
    assert result.startswith("hashed_")


def test_verify_password_returns_bool():
    hashed = crypto.hash_password("secret")
    assert crypto.verify_password("secret", hashed) is True
    assert crypto.verify_password("wrong", hashed) is False
    assert isinstance(crypto.verify_password("x", "y"), bool)


def test_encrypt_decrypt_returns_bytes_and_roundtrip():
    data = b"hello world"
    token = crypto.encrypt_data(data)
    assert isinstance(token, bytes)
    assert token.startswith(b"encrypted:")

    decrypted = crypto.decrypt_data(token)
    assert isinstance(decrypted, bytes)
    assert decrypted == data


def test_sign_verify_returns_bytes_and_bool():
    data = b"payload"
    signature = crypto.sign_data(data)
    assert isinstance(signature, bytes)
    assert signature.startswith(b"signature:")

    assert crypto.verify_signature(data, signature, b"pubkey") is True
    assert crypto.verify_signature(data, b"bad_signature", b"pubkey") is False
    assert isinstance(crypto.verify_signature(b"", b"", b""), bool)
