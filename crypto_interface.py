"""
Crypto interface stubs.
Week1: fake functions with correct type returns
Week2: realise Argon2id hashing and ChaCha20-Poly1305 + Ed25519 crypto
"""


def hash_password(password: str) -> str:
    return "hashed_" + password


def verify_password(password: str, hashed: str) -> bool:
    return hashed == "hashed_" + password


def encrypt_data(data: bytes) -> bytes:
    return b"encrypted:" + data


def decrypt_data(token: bytes) -> bytes:
    if token.startswith(b"encrypted:"):
        return token[len(b"encrypted:") :]
    return token


def sign_data(data: bytes, private_key: bytes = None) -> bytes:
    # stub for future usage
    _ = private_key
    return b"signature:" + data


def verify_signature(data: bytes, signature: bytes, public_key: bytes) -> bool:
    return signature == b"signature:" + data
