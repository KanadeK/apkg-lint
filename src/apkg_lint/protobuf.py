"""Tiny defensive protobuf wire decoder for the small APKG messages we need.

The project deliberately avoids generated Anki protobuf bindings.  Only package
metadata, media entries, and two notetype config messages are decoded. Unknown
fields are skipped according to the protobuf wire type, which keeps the parser
forward-compatible without pretending to understand new semantics.
"""

from __future__ import annotations

from dataclasses import dataclass


class ProtobufDecodeError(ValueError):
    """Raised when a protobuf payload is truncated or uses an unsupported wire type."""


_VARINT_CONTINUATION = 0x80
_WIRE_VARINT = 0
_WIRE_FIXED64 = 1
_WIRE_LENGTH_DELIMITED = 2
_WIRE_FIXED32 = 5


@dataclass(frozen=True)
class WireField:
    number: int
    wire_type: int
    value: int | bytes


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    for index in range(offset, min(len(data), offset + 10)):
        byte = data[index]
        value |= (byte & 0x7F) << shift
        if byte < _VARINT_CONTINUATION:
            return value, index + 1
        shift += 7
    raise ProtobufDecodeError("truncated or overlong varint")


def iter_fields(data: bytes) -> tuple[WireField, ...]:
    fields: list[WireField] = []
    offset = 0
    while offset < len(data):
        key, offset = decode_varint(data, offset)
        number = key >> 3
        wire_type = key & 0x07
        if number == 0:
            raise ProtobufDecodeError("field number 0 is invalid")
        value: int | bytes
        if wire_type == _WIRE_VARINT:
            value, offset = decode_varint(data, offset)
        elif wire_type == _WIRE_FIXED64:
            end = offset + 8
            if end > len(data):
                raise ProtobufDecodeError("truncated fixed64 field")
            value = data[offset:end]
            offset = end
        elif wire_type == _WIRE_LENGTH_DELIMITED:
            length, offset = decode_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ProtobufDecodeError("truncated length-delimited field")
            value = data[offset:end]
            offset = end
        elif wire_type == _WIRE_FIXED32:
            end = offset + 4
            if end > len(data):
                raise ProtobufDecodeError("truncated fixed32 field")
            value = data[offset:end]
            offset = end
        else:
            raise ProtobufDecodeError(f"unsupported protobuf wire type {wire_type}")
        fields.append(WireField(number=number, wire_type=wire_type, value=value))
    return tuple(fields)


def first_varint(data: bytes, number: int, default: int = 0) -> int:
    for field in iter_fields(data):
        if field.number == number and field.wire_type == _WIRE_VARINT:
            if not isinstance(field.value, int):
                raise ProtobufDecodeError("varint field carried non-integer data")
            return field.value
    return default


def first_bytes(data: bytes, number: int, default: bytes = b"") -> bytes:
    for field in iter_fields(data):
        if field.number == number and field.wire_type == _WIRE_LENGTH_DELIMITED:
            if not isinstance(field.value, bytes):
                raise ProtobufDecodeError("length-delimited field carried non-byte data")
            return field.value
    return default


def repeated_bytes(data: bytes, number: int) -> tuple[bytes, ...]:
    values: list[bytes] = []
    for field in iter_fields(data):
        if field.number == number and field.wire_type == _WIRE_LENGTH_DELIMITED:
            if not isinstance(field.value, bytes):
                raise ProtobufDecodeError("length-delimited field carried non-byte data")
            values.append(field.value)
    return tuple(values)


def decode_utf8(data: bytes, *, context: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtobufDecodeError(f"{context} is not valid UTF-8") from exc
