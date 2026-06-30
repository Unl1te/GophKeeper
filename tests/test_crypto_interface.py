import os

import pytest

import crypto_interface as crypto


def test_hash_password_returns_str():
    hashed = crypto.hash_password("test123")

    assert isinstance(hashed, str)
    assert hashed != "test123"
    assert crypto.verify_password("test123", hashed)


def test_verify_password_returns_bool():
    hashed = crypto.hash_password("secret")

    assert crypto.verify_password("secret", hashed) is True
    assert crypto.verify_password("wrong", hashed) is False


def test_hash_same_password_produces_different_hashes():
    hash1 = crypto.hash_password("secret")
    hash2 = crypto.hash_password("secret")

    assert hash1 != hash2

    assert crypto.verify_password("secret", hash1)
    assert crypto.verify_password("secret", hash2)


def test_hash_empty_password():
    hashed = crypto.hash_password("")

    assert isinstance(hashed, str)
    assert crypto.verify_password("", hashed)


def test_hash_special_characters():
    password = "p@ssW0rd!\n\t émoji🔥"

    hashed = crypto.hash_password(password)

    assert crypto.verify_password(password, hashed)


def test_hash_very_long_password():
    password = "a" * 10000

    hashed = crypto.hash_password(password)

    assert crypto.verify_password(password, hashed)


def test_derive_key_returns_32_bytes():
    salt = os.urandom(16)

    key = crypto.derive_key("password", salt)

    assert isinstance(key, bytes)
    assert len(key) == 32


def test_same_password_same_salt_same_key():
    salt = os.urandom(16)

    key1 = crypto.derive_key("password", salt)
    key2 = crypto.derive_key("password", salt)

    assert key1 == key2


def test_different_passwords_produce_different_keys():
    salt = os.urandom(16)

    key1 = crypto.derive_key("password1", salt)
    key2 = crypto.derive_key("password2", salt)

    assert key1 != key2


def test_different_salts_produce_different_keys():
    key1 = crypto.derive_key("password", os.urandom(16))
    key2 = crypto.derive_key("password", os.urandom(16))

    assert key1 != key2


def test_encrypt_decrypt_roundtrip():
    key = os.urandom(32)
    data = b"hello world"

    token = crypto.encrypt_data(data, key)

    assert isinstance(token, bytes)
    assert token != data

    decrypted = crypto.decrypt_data(token, key)

    assert decrypted == data


def test_encrypt_decrypt_empty_bytes():
    key = os.urandom(32)

    token = crypto.encrypt_data(b"", key)

    assert crypto.decrypt_data(token, key) == b""


def test_encrypt_decrypt_unicode_data():
    key = os.urandom(32)

    data = "Привет 😎🔐".encode("utf-8")

    token = crypto.encrypt_data(data, key)

    assert crypto.decrypt_data(token, key) == data


def test_encrypt_decrypt_binary_data():
    key = os.urandom(32)

    data = bytes(range(256)) * 100

    token = crypto.encrypt_data(data, key)

    assert crypto.decrypt_data(token, key) == data


def test_encrypt_decrypt_large_data():
    key = os.urandom(32)

    data = b"x" * (5 * 1024 * 1024)

    token = crypto.encrypt_data(data, key)

    assert crypto.decrypt_data(token, key) == data


def test_encrypt_same_data_twice_produces_different_ciphertexts():
    key = os.urandom(32)

    data = b"hello"

    token1 = crypto.encrypt_data(data, key)
    token2 = crypto.encrypt_data(data, key)

    # Different because of random nonce
    assert token1 != token2

    assert crypto.decrypt_data(token1, key) == data
    assert crypto.decrypt_data(token2, key) == data


def test_decrypt_with_wrong_key_fails():
    key1 = os.urandom(32)
    key2 = os.urandom(32)

    token = crypto.encrypt_data(b"secret", key1)

    with pytest.raises(Exception):
        crypto.decrypt_data(token, key2)


def test_sign_verify_returns_bytes_and_bool():
    data = b"payload"

    signature = crypto.sign_data(data)

    assert isinstance(signature, bytes)

    assert crypto.verify_signature(data, signature, b"pubkey")
    assert not crypto.verify_signature(data, b"bad_signature", b"pubkey")


def test_sign_empty_data():
    signature = crypto.sign_data(b"")

    assert crypto.verify_signature(b"", signature, b"pubkey")


def test_sign_large_data():
    data = b"x" * (5 * 1024 * 1024)

    signature = crypto.sign_data(data)

    assert crypto.verify_signature(data, signature, b"pubkey")
