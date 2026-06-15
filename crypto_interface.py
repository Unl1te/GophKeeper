def hash_password(password: str) -> str:
    """Stub: password hashing (will use bcrypt in the future)."""
    return f"hashed_{password}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Stub: password verification."""
    return hashed_password == f"hashed_{plain_password}"


def encrypt_data(data: bytes, key: bytes) -> bytes:
    """Stub: data encryption (will use Fernet/AES in the future)."""
    return b"encrypted_" + data


def decrypt_data(encrypted_data: bytes, key: bytes) -> bytes:
    """Stub: data decryption."""
    return encrypted_data.replace(b"encrypted_", b"")


def sign_data(data: str) -> str:
    """Stub: digital signature creation."""
    return f"signature_for_{data}"
