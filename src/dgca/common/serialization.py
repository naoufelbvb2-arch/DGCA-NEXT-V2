"""Canonical big-endian IEEE-754 binary64 and schema record serialization for DGCA v2.

Normative references:
- DGCA_CORE_RC4_1.md §3.1 (Numeric and sort contract)
- R2-A01-IMPLEMENTATION-PLAN.md §2 (Patch 5: Manifest Generator & Durable Persistence Boundary Isolation)
- R2-A01-REMEDIATION-DESIGN-CONTRACT.md §3.4 (Durable Persistence Boundaries)
"""

from __future__ import annotations

import math
import struct
from typing import Protocol, runtime_checkable

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


@runtime_checkable
class DurablePersistenceService(Protocol):
    """Formal interface boundary declaration for future durable persistence (R1-B03 scope).

    ### Architectural Boundary & Invariant Distinction

    The current DGCA NEXT V2 system (R2-A01) guarantees in-process transaction atomicity
    and memory-space consistency within a single executing process runtime:
    - Transactional shadow preparation (private memory staging via w_shadow).
    - In-process publication consistency (atomic single pointer swap via TransactionPublicationView).
    - Completed-root registration (frozendict registry in TransactionPublicationView.completed_roots).
    - Pending outbox retention in memory (TransactionPublicationView.pending_outbox_by_root).
    - Explicit outbox reconciliation (ExposureTransactionManager.reconcile_outbox() API).
    - Per-notification rollback and idempotency (SurfaceReadoutLedgerV1 canonical evidence checks).
    - Read-only scientific state verification (zero-mutation invariant on W, H_slow, and ledger).

    ### Durability Non-Guarantees (Explicit Boundary Limitations)

    The current in-process architecture does NOT guarantee, and cannot guarantee without
    an external durable persistence implementation:
    - Recovery after process termination (SIGKILL, unhandled exception, segfault, clean exit).
    - Recovery after OS crashes, kernel panics, or system reboots.
    - Survivability against machine power failure or volatile memory loss.
    - Invariance against loss of unpersisted RAM contents.
    - Cross-process restart without durable storage.
    - Crash recovery without a durable transaction journal or Write-Ahead Log (WAL).

    ### Scope Enforcement (Zero Durability Implementation in R2-A01)

    In accordance with the frozen R2-A01 Implementation Plan and Remediation Contract,
    no durable persistence engine, persistent database, WAL, background sync worker,
    or restart transaction replay is implemented within this module or patch.
    This interface serves strictly as an architectural specification boundary for future
    scope (R1-B03).
    """

    def persist_record(
        self,
        record_tag_u8: int,
        schema_version_u8: int,
        payload: bytes,
    ) -> None:
        """Persist a canonical serialized record envelope to durable storage.

        Note: Formal boundary declaration only. Implementation deferred to R1-B03.
        """
        ...

    def recover_records(
        self,
        record_tag_u8: int | None = None,
    ) -> list[tuple[int, int, bytes]]:
        """Recover persisted records from durable storage.

        Note: Formal boundary declaration only. Implementation deferred to R1-B03.
        """
        ...

