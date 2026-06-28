import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False


def encrypt_data(data: bytes, key: bytes) -> bytes:
    cipher = ChaCha20Poly1305(key)

    nonce = os.urandom(12)
    encrypted = cipher.encrypt(nonce, data, None)
    return nonce + encrypted


def decrypt_data(token: bytes, key: bytes) -> bytes:
    nonce = token[:12]
    ciphertext = token[12:]

    cipher = ChaCha20Poly1305(key)
    return cipher.decrypt(nonce, ciphertext, None)


def derive_key(password: str, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=password.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        type=Type.ID,
    )


def sign_data(data: bytes, private_key: bytes = None) -> bytes:
    # stub for future usage
    _ = private_key
    return b"signature:" + data


def verify_signature(data: bytes, signature: bytes, public_key: bytes) -> bool:
    return signature == b"signature:" + data
