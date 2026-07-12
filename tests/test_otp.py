"""
Unit tests for the OTP (TOTP) helper functions added to crypto_interface.py
(issue #29).

No network/server needed — pure unit tests against the crypto module.

Time-window behaviour is tested using pyotp's own `TOTP.at(datetime)`
method to construct a code for an arbitrary point in time, rather than
mocking a clock. An earlier version of this file tried to control time by
patching `time.time()`, which silently did nothing: pyotp's `now()`/
`verify()` get the current time via `datetime.datetime.now()` internally,
not `time.time()`, so the patch never took effect and several of these
tests were passing for the wrong reason (every call was actually landing
in the same real, un-mocked instant). Using `.at()` sidesteps the question
of which clock function pyotp uses internally entirely, and is fully
deterministic: it's a pure function of the datetime you pass it.

Run with:
    pytest tests/test_otp.py -v
"""
import datetime

import pyotp
import pytest

import crypto_interface as crypto


def _code_at(secret: str, when: datetime.datetime) -> str:
    """Build the TOTP code that would be valid at `when`, without touching
    any clock — uses pyotp's own for_time support (public, documented API,
    stable regardless of pyotp's internal clock source)."""
    return pyotp.TOTP(secret).at(when)


def test_generate_otp_secret_returns_str():
    secret = crypto.generate_otp_secret()
    assert isinstance(secret, str)
    assert len(secret) > 0


def test_generate_otp_secret_is_valid_base32():
    import base64

    secret = crypto.generate_otp_secret()
    padded = secret + "=" * (-len(secret) % 8)
    decoded = base64.b32decode(padded)
    assert (
        len(decoded) >= 10
    )  # pyotp defaults to 160 bits (20 bytes); RFC 4226 requires >= 128 bits (16 bytes)


def test_generate_otp_secret_is_random():
    secret1 = crypto.generate_otp_secret()
    secret2 = crypto.generate_otp_secret()
    assert secret1 != secret2


def test_get_totp_code_returns_six_digits():
    secret = crypto.generate_otp_secret()
    code = crypto.get_totp_code(secret)
    assert isinstance(code, str)
    assert len(code) == 6
    assert code.isdigit()


def test_get_totp_code_deterministic_within_same_time_step():
    """Two calls made back-to-back (microseconds apart) should return the
    same code — real time, no mocking needed, since 30s is an eternity
    compared to how long two function calls take."""
    secret = crypto.generate_otp_secret()
    code1 = crypto.get_totp_code(secret)
    code2 = crypto.get_totp_code(secret)
    assert code1 == code2


def test_totp_code_changes_across_time_steps():
    """The underlying TOTP scheme: a code for step N differs from step N+1.
    Uses .at() against a single fixed reference instant, so it's a pure
    function of that reference and can never be flaky."""
    secret = crypto.generate_otp_secret()
    reference = datetime.datetime.now()
    code_t0 = _code_at(secret, reference)
    code_t1 = _code_at(secret, reference + datetime.timedelta(seconds=30))
    assert code_t0 != code_t1


def test_different_secrets_produce_different_codes():
    secret1 = crypto.generate_otp_secret()
    secret2 = crypto.generate_otp_secret()
    code1 = crypto.get_totp_code(secret1)
    code2 = crypto.get_totp_code(secret2)
    assert code1 != code2


def test_verify_totp_accepts_correct_code():
    secret = crypto.generate_otp_secret()
    code = crypto.get_totp_code(secret)
    assert crypto.verify_totp(secret, code) is True


def test_verify_totp_rejects_wrong_code():
    secret = crypto.generate_otp_secret()
    code = crypto.get_totp_code(secret)
    wrong_code = "0" * 6 if code != "0" * 6 else "1" * 6
    assert crypto.verify_totp(secret, wrong_code) is False


def test_verify_totp_rejects_code_from_wrong_secret():
    secret_a = crypto.generate_otp_secret()
    secret_b = crypto.generate_otp_secret()
    code_for_a = crypto.get_totp_code(secret_a)
    assert crypto.verify_totp(secret_b, code_for_a) is False


def test_verify_totp_rejects_malformed_code():
    secret = crypto.generate_otp_secret()
    assert crypto.verify_totp(secret, "not-a-code") is False
    assert crypto.verify_totp(secret, "") is False


def test_verify_totp_allows_one_step_of_clock_drift():
    """verify_totp uses valid_window=1, so a code generated one 30s step
    in the past (or future) relative to right now should still verify —
    this is what makes TOTP usable when client/server clocks aren't
    perfectly synced."""
    secret = crypto.generate_otp_secret()
    now = datetime.datetime.now()

    code_previous_step = _code_at(secret, now - datetime.timedelta(seconds=30))
    code_next_step = _code_at(secret, now + datetime.timedelta(seconds=30))

    assert crypto.verify_totp(secret, code_previous_step) is True
    assert crypto.verify_totp(secret, code_next_step) is True


def test_verify_totp_rejects_code_outside_the_window():
    """A code from 5 time-steps (150s) in the past must NOT verify right
    now — otherwise a leaked/observed code would stay valid far too long."""
    secret = crypto.generate_otp_secret()
    now = datetime.datetime.now()

    old_code = _code_at(secret, now - datetime.timedelta(seconds=150))
    assert crypto.verify_totp(secret, old_code) is False


def test_verify_totp_rejects_future_code_not_yet_valid():
    """Sanity check the other direction: a code that will only become
    valid an hour from now must not verify right now — confirms
    verify_totp isn't accidentally accepting arbitrary/lenient input."""
    secret = crypto.generate_otp_secret()
    now = datetime.datetime.now()

    code_now = _code_at(secret, now)
    code_much_later = _code_at(secret, now + datetime.timedelta(hours=1))

    assert crypto.verify_totp(secret, code_now) is True
    assert crypto.verify_totp(secret, code_much_later) is False
