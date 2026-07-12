"""
POC client demonstrating a --binary flag against the MessagePack
proof-of-concept endpoints added in app/api/routes/binary_poc.py (#31).

Standalone demo, not a patch to cli.py, for the same reason as
otp_cli_example.py: cli.py has grown a lot in the latest merge and I don't
have its current full contents, so I can't safely splice a new flag into
its existing argument parsing without risking a conflict. The pattern below
(swap json<->msgpack (de)serialization based on a --binary flag, and hit
/items-binary/ instead of /items/) is exactly what you'd add to cli.py's
add_item()/get_item() once you're happy with the POC.

Usage:
    python binary_protocol_client_demo.py --token TOKEN add --type text --content "hello"
    python binary_protocol_client_demo.py --token TOKEN --binary add --type text --content "hello"
"""
import argparse
import json
import sys

import msgpack
import requests

SERVER_URL = "http://localhost:8000"


def add_item(token: str, item_type: str, content: str, use_binary: bool) -> None:
    content_bytes = content.encode("utf-8")

    if use_binary:
        body = msgpack.packb(
            {"type": item_type, "content": content_bytes, "metadata": {}},
            use_bin_type=True,
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/msgpack",
        }
        resp = requests.post(f"{SERVER_URL}/items-binary/", data=body, headers=headers)
        wire_bytes_sent = len(body)
        result = msgpack.unpackb(resp.content, raw=False) if resp.ok else resp.text
    else:
        json_body = {"type": item_type, "content": content_bytes.hex(), "metadata": {}}
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(f"{SERVER_URL}/items/", json=json_body, headers=headers)
        wire_bytes_sent = len(json.dumps(json_body))
        result = resp.json() if resp.ok else resp.text

    protocol = "msgpack" if use_binary else "json"
    print(
        f"[{protocol}] status={resp.status_code} request_body_bytes={wire_bytes_sent}"
    )
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--binary",
        action="store_true",
        help="Use the MessagePack POC endpoint instead of JSON",
    )
    parser.add_argument("--token", required=True, help="Bearer token from POST /login")
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add")
    add_p.add_argument("--type", required=True)
    add_p.add_argument("--content", required=True)

    args = parser.parse_args()

    if args.command == "add":
        add_item(args.token, args.type, args.content, args.binary)


if __name__ == "__main__":
    main()
