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

def test_hash_empty_password():
    result = crypto.hash_password("")
    assert isinstance(result, str)
    assert result == "hashed_"


def test_verify_empty_password():
    hashed = crypto.hash_password("")
    assert crypto.verify_password("", hashed) is True
    assert crypto.verify_password("wrong", hashed) is False


def test_encrypt_decrypt_empty_bytes():
    data = b""
    token = crypto.encrypt_data(data)
    assert token == b"encrypted:"
    decrypted = crypto.decrypt_data(token)
    assert decrypted == b""


def test_sign_empty_data():
    signature = crypto.sign_data(b"")
    assert signature == b"signature:"
    assert crypto.verify_signature(b"", signature, b"pubkey") is True


def test_hash_special_characters():
    password = "p@ssW0rd!\n\t émoji💩🔥"
    hashed = crypto.hash_password(password)
    assert hashed == "hashed_" + password
    assert crypto.verify_password(password, hashed) is True


def test_encrypt_decrypt_unicode_data():
    data = "Привет, мир! Данные пользователя 😎🔐".encode("utf-8")
    token = crypto.encrypt_data(data)
    assert token.startswith(b"encrypted:")
    decrypted = crypto.decrypt_data(token)
    assert decrypted == data


def test_sign_verify_unicode_data():
    data = "команда: сохранить 💾".encode("utf-8")
    signature = crypto.sign_data(data)
    assert signature == b"signature:" + data
    assert crypto.verify_signature(data, signature, b"pubkey") is True


def test_verify_password_special_chars():
    password = "pass\nwith\ttabs and\r\nnewlines"
    hashed = crypto.hash_password(password)
    assert crypto.verify_password(password, hashed) is True
    assert crypto.verify_password("wrong", hashed) is False


def test_encrypt_decrypt_large_data():
    data = b"x" * (11 * 1024 * 1024) 
    token = crypto.encrypt_data(data)
    assert isinstance(token, bytes)
    assert token.startswith(b"encrypted:")
    assert len(token) == len(b"encrypted:") + len(data)
    decrypted = crypto.decrypt_data(token)
    assert decrypted == data


def test_sign_large_data():
    data = b"y" * (10 * 1024 * 1024)  
    signature = crypto.sign_data(data)
    assert isinstance(signature, bytes)
    assert signature.startswith(b"signature:")
    assert crypto.verify_signature(data, signature, b"pubkey") is True


def test_encrypt_decrypt_binary_data():
    data = bytes(range(256)) * 100  
    token = crypto.encrypt_data(data)
    decrypted = crypto.decrypt_data(token)
    assert decrypted == data


def test_hash_very_long_password():
    password = "a" * 10000
    hashed = crypto.hash_password(password)
    assert isinstance(hashed, str)
    assert hashed.startswith("hashed_")
    assert crypto.verify_password(password, hashed) is True


def test_decrypt_unencrypted_data():
    data = b"raw data without prefix"
    result = crypto.decrypt_data(data)
    assert result == data


def test_verify_signature_wrong_key():
    data = b"payload"
    signature = crypto.sign_data(data)
    result = crypto.verify_signature(data, signature, b"wrong_key")
    assert isinstance(result, bool)
    assert result is True 


def test_original_tests_still_pass():
    result = crypto.hash_password("test123")
    assert isinstance(result, str)
    assert result.startswith("hashed_")

    hashed = crypto.hash_password("secret")
    assert crypto.verify_password("secret", hashed) is True
    assert crypto.verify_password("wrong", hashed) is False

    data = b"hello world"
    token = crypto.encrypt_data(data)
    assert isinstance(token, bytes)
    assert crypto.decrypt_data(token) == data

    signature = crypto.sign_data(b"payload")
    assert crypto.verify_signature(b"payload", signature, b"pubkey") is True
