from __future__ import annotations

import pytest

from apkg_lint.protobuf import (
    ProtobufDecodeError,
    decode_utf8,
    decode_varint,
    first_bytes,
    first_varint,
    iter_fields,
    repeated_bytes,
)


def _varint(value: int) -> bytes:
    output = bytearray()
    while value >= 0x80:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def test_decodes_supported_wire_types_and_accessors() -> None:
    payload = (
        _varint(1 << 3)
        + _varint(300)
        + _varint((2 << 3) | 2)
        + _varint(3)
        + b"one"
        + _varint((2 << 3) | 2)
        + _varint(3)
        + b"two"
        + _varint((3 << 3) | 1)
        + b"12345678"
        + _varint((4 << 3) | 5)
        + b"1234"
    )
    fields = iter_fields(payload)
    assert len(fields) == 5
    assert first_varint(payload, 1) == 300
    assert first_varint(payload, 99, 7) == 7
    assert first_bytes(payload, 2) == b"one"
    assert first_bytes(payload, 99, b"default") == b"default"
    assert repeated_bytes(payload, 2) == (b"one", b"two")
    assert decode_utf8(b"hello", context="test") == "hello"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\x80", "varint"),
        (b"\x00", "field number 0"),
        (b"\x0b", "wire type"),
        (b"\x09short", "fixed64"),
        (b"\x0dxx", "fixed32"),
        (b"\x0a\x05xx", "length-delimited"),
    ],
)
def test_rejects_malformed_wire_payloads(payload: bytes, message: str) -> None:
    with pytest.raises(ProtobufDecodeError, match=message):
        iter_fields(payload)


def test_decode_varint_offset_and_overlong() -> None:
    assert decode_varint(b"x\x96\x01", 1) == (150, 3)
    with pytest.raises(ProtobufDecodeError, match="overlong"):
        decode_varint(b"\x80" * 11)


def test_rejects_invalid_utf8() -> None:
    with pytest.raises(ProtobufDecodeError, match="not valid UTF-8"):
        decode_utf8(b"\xff", context="name")
