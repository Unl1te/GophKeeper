"""
Tests and measurements for the MessagePack binary-protocol POC (issue #31).

Two kinds of checks here:
  1. Wire-format unit tests (no server needed) — confirm the msgpack
     payload round-trips and that binary content survives without the
     hex-encoding step the JSON API needs.
  2. A measured size comparison between JSON+hex and msgpack for the same
     ciphertext, backing up the "why bother with a binary protocol" claim
     with actual numbers instead of a general assertion.

Run with:
    pytest tests/test_binary_protocol_poc.py -v -s
"""
import json

import msgpack
import pytest


def _json_hex_request_size(content: bytes, metadata: dict | None = None) -> int:
    body = {"type": "binary", "content": content.hex(), "metadata": metadata or {}}
    return len(json.dumps(body).encode("utf-8"))


def _msgpack_request_size(content: bytes, metadata: dict | None = None) -> int:
    body = {"type": "binary", "content": content, "metadata": metadata or {}}
    return len(msgpack.packb(body, use_bin_type=True))


@pytest.mark.parametrize(
    "size", [64, 1024, 64 * 1024, 1024 * 1024], ids=["64B", "1KB", "64KB", "1MB"]
)
def test_msgpack_payload_is_smaller_than_json_hex(size):
    content = bytes(range(256)) * (size // 256 + 1)
    content = content[:size]

    json_size = _json_hex_request_size(content)
    msgpack_size = _msgpack_request_size(content)

    # JSON+hex must be roughly double: 2 hex chars per byte, vs msgpack's
    # native binary type (a handful of framing bytes, not per-byte cost).
    assert msgpack_size < json_size
    ratio = json_size / msgpack_size
    print(
        f"\n[{size} bytes] json+hex={json_size} msgpack={msgpack_size} ratio={ratio:.2f}x"
    )
    assert (
        ratio > 1.7
    ), "expected roughly a 2x size reduction from dropping hex encoding"


def test_msgpack_roundtrip_preserves_binary_content_exactly():
    content = bytes(range(256)) * 10  # includes every byte value, incl. non-UTF8 ones
    packed = msgpack.packb(
        {"type": "binary", "content": content, "metadata": {}}, use_bin_type=True
    )
    unpacked = msgpack.unpackb(packed, raw=False)

    assert unpacked["content"] == content
    assert isinstance(unpacked["content"], bytes)


def test_msgpack_roundtrip_preserves_metadata():
    metadata = {"note": "test", "count": 3, "nested": {"a": [1, 2, 3]}}
    packed = msgpack.packb(
        {"type": "text", "content": b"x", "metadata": metadata}, use_bin_type=True
    )
    unpacked = msgpack.unpackb(packed, raw=False)

    assert unpacked["metadata"] == metadata


def test_msgpack_rejects_malformed_bytes():
    with pytest.raises(Exception):
        msgpack.unpackb(b"\xff\xff\xff not valid msgpack", raw=False)
