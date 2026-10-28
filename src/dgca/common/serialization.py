"""Canonical big-endian IEEE-754 binary64 and schema record serialization for DGCA v2.

Normative reference:
- DGCA_CORE_RC4_1.md §3.1 (Numeric and sort contract)
"""

from __future__ import annotations

import math
import struct

from dgca.common.errors import SerializationError, StatusCode
from dgca.common.numeric import validate_finite_binary64


def pack_binary64_be(x: float) -> bytes:
    """Pack a finite IEEE-754 binary64 float as canonical 8-byte big-endian, normalizing -0.0 to +0.0."""
    try:
        val = validate_finite_binary64(x)
    except Exception as exc:
        raise SerializationError(str(exc), code=StatusCode.INVALID_NUMERIC_VALUE) from exc
    if val == 0.0:
        return b"\x00\x00\x00\x00\x00\x00\x00\x00"
    return struct.pack(">d", val)


def unpack_binary64_be(data: bytes, offset: int = 0) -> tuple[float, int]:
    """Unpack a canonical 8-byte big-endian IEEE-754 binary64 float, rejecting NaN/Inf and normalizing -0.0."""
    if len(data) - offset < 8:
        raise SerializationError("Insufficient bytes for binary64 unpacking")
    val = struct.unpack_from(">d", data, offset)[0]
    if math.isnan(val) or math.isinf(val):
        raise SerializationError(
            f"Deserialized non-finite float: {val!r}",
            code=StatusCode.INVALID_NUMERIC_VALUE,
        )
    if val == 0.0:
        val = 0.0
    return val, offset + 8


def pack_record_envelope(
    record_tag_u8: int,
    schema_version_u8: int,
    payload: bytes,
) -> bytes:
    """Pack a schema record envelope: record_tag_u8 || schema_version_u8 || payload_length_u32_BE || payload."""
    if not (0 <= record_tag_u8 <= 0xFF):
        raise SerializationError(f"record_tag_u8 out of range: {record_tag_u8}")
    if not (0 <= schema_version_u8 <= 0xFF):
        raise SerializationError(f"schema_version_u8 out of range: {schema_version_u8}")
    return struct.pack(">BBI", record_tag_u8, schema_version_u8, len(payload)) + payload


def unpack_record_envelope(data: bytes, offset: int = 0) -> tuple[int, int, bytes, int]:
    """Unpack a schema record envelope and return (record_tag_u8, schema_version_u8, payload, next_offset)."""
    if len(data) - offset < 6:
        raise SerializationError("Insufficient bytes for record envelope header")
    record_tag_u8, schema_version_u8, payload_len = struct.unpack_from(">BBI", data, offset)
    start = offset + 6
    end = start + payload_len
    if end > len(data):
        raise SerializationError(
            f"Truncated record payload: expected {payload_len} bytes, got {len(data) - start}"
        )
    return record_tag_u8, schema_version_u8, data[start:end], end
