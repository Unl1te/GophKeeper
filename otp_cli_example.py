"""
Standalone example of how the OTP functions from crypto_interface.py could
be used from a CLI (issue #29, "example usage for CLI" — optional).

This is deliberately NOT a patch to cli.py: cli.py has grown substantially
in the latest merge and I don't have its current full contents, so I can't
safely splice a new subcommand into its existing argument parsing without
risking a conflict. This script shows the calling pattern in isolation;
wiring it into the real cli.py (deciding on a DataType/storage model for
OTP secrets, etc.) is a separate design decision beyond what #29 asks for.

Usage:
    python otp_cli_example.py new
    python otp_cli_example.py code <SECRET>
    python otp_cli_example.py verify <SECRET>
"""
import sys

import crypto_interface as crypto


def otp_new() -> None:
    secret = crypto.generate_otp_secret()
    print(f"New OTP secret (store this securely, e.g. as an encrypted item): {secret}")
    print(f"Current code: {crypto.get_totp_code(secret)}")


def otp_code(secret: str) -> None:
    print(crypto.get_totp_code(secret))


def otp_verify(secret: str) -> None:
    code = input("Enter the 6-digit code from your authenticator app: ").strip()
    if crypto.verify_totp(secret, code):
        print("Valid \u2713")
    else:
        print("Invalid \u2717")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "new":
        otp_new()
    elif command == "code" and len(sys.argv) == 3:
        otp_code(sys.argv[2])
    elif command == "verify" and len(sys.argv) == 3:
        otp_verify(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
