from crypto_interface import encrypt_data, hash_password


def test_hash_password_types():
    """Check that the hash is returned as a string."""
    result = hash_password("secret")
    assert isinstance(result, str)
    assert result == "hashed_secret"


def test_encrypt_data_types():
    """Check that encryption returns bytes."""
    result = encrypt_data(b"my_data", b"my_key")
    assert isinstance(result, bytes)
    assert result == b"encrypted_my_data"
