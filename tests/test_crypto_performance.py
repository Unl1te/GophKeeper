import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from crypto_interface import encrypt_data, decrypt_data, derive_key

KEY = derive_key("perf-test-master-password", b"gophkeeper_salt_16bytes")

SIZES = [
    ("64KB", 64 * 1024, 0.5),
    ("1MB", 1 * 1024 * 1024, 1.0),
    ("10MB", 10 * 1024 * 1024, 3.0),
]


def _run_case(size_bytes: int, budget_seconds: float, label: str):
    data = os.urandom(size_bytes)

    t0 = time.perf_counter()
    encrypted = encrypt_data(data, KEY)
    t1 = time.perf_counter()
    decrypted = decrypt_data(encrypted, KEY)
    t2 = time.perf_counter()

    encrypt_time = t1 - t0
    decrypt_time = t2 - t1
    total_time = t2 - t0

    assert decrypted == data, f"round-trip mismatch for {label} payload"

    mb = size_bytes / (1024 * 1024)
    enc_throughput = mb / encrypt_time if encrypt_time > 0 else float("inf")
    dec_throughput = mb / decrypt_time if decrypt_time > 0 else float("inf")
    print(
        f"[{label:>6}] encrypt: {encrypt_time * 1000:8.2f} ms "
        f"({enc_throughput:8.1f} MB/s)  "
        f"decrypt: {decrypt_time * 1000:8.2f} ms "
        f"({dec_throughput:8.1f} MB/s)"
    )

    assert total_time < budget_seconds, (
        f"encrypt+decrypt of {label} took {total_time:.3f}s, "
        f"exceeding the {budget_seconds}s budget"
    )


@pytest.mark.parametrize(
    "label,size_bytes,budget_seconds", SIZES, ids=[s[0] for s in SIZES]
)
def test_encrypt_decrypt_roundtrip_performance(label, size_bytes, budget_seconds):
    _run_case(size_bytes, budget_seconds, label)


def test_repeated_10mb_operations_stay_fast():
    size_bytes = 10 * 1024 * 1024
    per_call_budget = 3.0
    n_iterations = 5

    data = os.urandom(size_bytes)
    total_start = time.perf_counter()
    for i in range(n_iterations):
        t0 = time.perf_counter()
        encrypted = encrypt_data(data, KEY)
        decrypted = decrypt_data(encrypted, KEY)
        elapsed = time.perf_counter() - t0

        assert decrypted == data, f"round-trip mismatch on iteration {i}"
        assert elapsed < per_call_budget, (
            f"iteration {i} took {elapsed:.3f}s, exceeding {per_call_budget}s budget "
            "(possible perf regression under repeated load)"
        )
    total_elapsed = time.perf_counter() - total_start
    print(
        f"\n[10MB x{n_iterations}] total: {total_elapsed:.2f}s, "
        f"avg: {total_elapsed / n_iterations * 1000:.1f} ms/iteration"
    )


def test_ciphertext_overhead_is_constant_regardless_of_size():
    for size_bytes in (0, 1024, 1024 * 1024, 10 * 1024 * 1024):
        data = os.urandom(size_bytes)
        encrypted = encrypt_data(data, KEY)
        overhead = len(encrypted) - len(data)
        assert overhead == 12 + 16, (
            f"unexpected ciphertext overhead {overhead} bytes for a "
            f"{size_bytes}-byte payload (expected 28: 12-byte nonce + 16-byte tag)"
        )


def test_different_nonces_for_repeated_encryption_of_same_large_payload():
    data = os.urandom(5 * 1024 * 1024)
    encrypted_1 = encrypt_data(data, KEY)
    encrypted_2 = encrypt_data(data, KEY)
    assert (
        encrypted_1[:12] != encrypted_2[:12]
    ), "nonce reuse detected on repeated encryption"
    assert encrypted_1 != encrypted_2
    assert decrypt_data(encrypted_1, KEY) == data
    assert decrypt_data(encrypted_2, KEY) == data


if __name__ == "__main__":
    for label, size_bytes, _budget in SIZES:
        _run_case(size_bytes, budget_seconds=float("inf"), label=label)
