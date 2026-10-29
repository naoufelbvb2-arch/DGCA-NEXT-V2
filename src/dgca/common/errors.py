"""Normative status codes, diagnostics, and exceptions for DGCA v2 (RC4.1)."""

from __future__ import annotations

from enum import StrEnum


class StatusCode(StrEnum):
    """Canonical diagnostic and error codes across Encoder, Core, and LLA."""

    # General / Success
    OK = "OK"

    # Encoder errors (DGCA-DCR-ENCODER-SPEC §1, §2, §5.2)
    INVALID_ENCODER_INPUT = "INVALID_ENCODER_INPUT"
    RESERVED_CONTROL_BYTE = "RESERVED_CONTROL_BYTE"
    EMPTY_EXPOSURE_INPUT = "EMPTY_EXPOSURE_INPUT"
    EMPTY_LEXICAL_EXPOSURE = "EMPTY_LEXICAL_EXPOSURE"
    TOKEN_TOO_LONG = "TOKEN_TOO_LONG"

    # Core SIC-V1 & Observation errors (Core §3.1, LLA §2.1)
    INVALID_OBSERVATION = "INVALID_OBSERVATION"
    INVALID_NUMERIC_VALUE = "INVALID_NUMERIC_VALUE"
    INVALID_SERIALIZATION = "INVALID_SERIALIZATION"
    CELL_FEATURE_ALIAS = "CELL_FEATURE_ALIAS"
    UNSPECIFIED_OPERATOR = "UNSPECIFIED_OPERATOR"

    # Transaction & Provenance errors (R2-A01 Patch 1)
    PROVENANCE_DIGEST_MISMATCH = "PROVENANCE_DIGEST_MISMATCH"
    PROVENANCE_MARKER_MISMATCH = "PROVENANCE_MARKER_MISMATCH"
    PROVENANCE_FEATURE_COPY_MISMATCH = "PROVENANCE_FEATURE_COPY_MISMATCH"
    PROVENANCE_ENVELOPE_MISSING = "PROVENANCE_ENVELOPE_MISSING"
    INVALID_SURFACE_HASH = "INVALID_SURFACE_HASH"
    EVENT_RETRY_PAYLOAD_CONFLICT = "EVENT_RETRY_PAYLOAD_CONFLICT"
    EVENT_RETRY_PROVENANCE_ALTERATION = "EVENT_RETRY_PROVENANCE_ALTERATION"

    # Latent & Capacity diagnostics (Core §1.3, §7.3, LLA §5)
    RECYCLE_BLOCKED_CANDIDATE = "RECYCLE_BLOCKED_CANDIDATE"
    STALE_LATENT_ELIGIBILITY = "STALE_LATENT_ELIGIBILITY"
    NO_DISCRIMINATIVE_PREDECESSOR_WITHIN_FRONTIER = "NO_DISCRIMINATIVE_PREDECESSOR_WITHIN_FRONTIER"
    SOURCE_OUTGOING_CAPACITY = "SOURCE_OUTGOING_CAPACITY"
    NO_FREE_CONTEXT_CELL = "NO_FREE_CONTEXT_CELL"
    NO_FEASIBLE_2_2_2_WITHIN_FRONTIER = "NO_FEASIBLE_2_2_2_WITHIN_FRONTIER"
    ANCHOR_CONTEXT_TOO_WIDE = "ANCHOR_CONTEXT_TOO_WIDE"

    # Context Gate & Routing diagnostics (Core §5.1, §5.2, §6.1)
    INVALID_CONTEXT_THRESHOLD = "INVALID_CONTEXT_THRESHOLD"
    CONTEXT_GATE_BYPASS = "CONTEXT_GATE_BYPASS"
    MISSING_CONTEXT_SOURCE = "MISSING_CONTEXT_SOURCE"
    STALE_CONTEXT_BINDING = "STALE_CONTEXT_BINDING"
    AMBIGUOUS_CONTEXT_OWNER = "AMBIGUOUS_CONTEXT_OWNER"
    DERIVED_PROVENANCE_UNVERIFIED = "DERIVED_PROVENANCE_UNVERIFIED"
    PARENT_NOT_COMPLETE = "PARENT_NOT_COMPLETE"
    CONTEXT_CHAIN_DEPTH_EXCEEDED = "CONTEXT_CHAIN_DEPTH_EXCEEDED"
    PARENT_BINDING_STALE = "PARENT_BINDING_STALE"
    CONTEXT_CHAIN_CYCLE = "CONTEXT_CHAIN_CYCLE"

    # Contrast & Owner Resolution (Core §7.1, §7.2, §7.7, LLA §2.1)
    NOT_EVALUATED_NO_COMPARATOR = "NOT_EVALUATED_NO_COMPARATOR"
    UNRESOLVED_COVERAGE = "UNRESOLVED_COVERAGE"
    UNRESOLVED_COLLISION = "UNRESOLVED_COLLISION"
    NO_CONTRAST = "NO_CONTRAST"
    UNRESOLVED = "UNRESOLVED"
    REUSE = "REUSE"
    NEW_ELIGIBLE = "NEW_ELIGIBLE"
    UNRESOLVED_BRANCH_MATCH = "UNRESOLVED_BRANCH_MATCH"
    STALE_OWNER_BINDING = "STALE_OWNER_BINDING"
    OWNER_REGISTRY_CONFLICT = "OWNER_REGISTRY_CONFLICT"
    OWNER_REGISTRY_CAPACITY = "OWNER_REGISTRY_CAPACITY"

    # Candidate Probation & C04 Graduation (Core §7.4, §7.6, LLA §6.3, §6.4)
    NO_PROBE_INSUFFICIENT_DRIVE = "NO_PROBE_INSUFFICIENT_DRIVE"
    NO_PROBE_FAIL = "NO_PROBE_FAIL"
    DURABILITY_PENDING = "DURABILITY_PENDING"
    RETIREMENT_SEMANTICS_DRIFT = "RETIREMENT_SEMANTICS_DRIFT"
    UNSUPPORTED_BINDING_SCHEMA = "UNSUPPORTED_BINDING_SCHEMA"
    CONFLICT_NEUTRALIZED = "CONFLICT_NEUTRALIZED"
    UNVERIFIED = "UNVERIFIED"

    # Transaction & Orchestration (Core §10.2, R2-A01 Patch 4)
    OUTBOX_DELIVERY_PENDING = "OUTBOX_DELIVERY_PENDING"

    # Assembly & Readout (Core §2.0, §9.2, §9.3, §9.4)
    NO_RECIPROCAL_TRIANGLE = "NO_RECIPROCAL_TRIANGLE"
    NO_ASSEMBLY = "NO_ASSEMBLY"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    READOUT_UNKNOWN = "READOUT_UNKNOWN"
    READOUT_AMBIGUOUS = "READOUT_AMBIGUOUS"
    READOUT_AMBIGUOUS_PENDING = "READOUT_AMBIGUOUS_PENDING"
    READOUT_UNAVAILABLE = "READOUT_UNAVAILABLE"

    # Generation stop codes (Core §9.3)
    GEN_STOP_EOS = "GEN_STOP_EOS"
    GEN_STOP_NO_ASSEMBLY = "GEN_STOP_NO_ASSEMBLY"
    GEN_STOP_NO_MATCH = "GEN_STOP_NO_MATCH"
    GEN_STOP_AMBIGUOUS = "GEN_STOP_AMBIGUOUS"
    GEN_STOP_READOUT_UNKNOWN = "GEN_STOP_READOUT_UNKNOWN"
    GEN_STOP_READOUT_AMBIGUOUS = "GEN_STOP_READOUT_AMBIGUOUS"
    GEN_STOP_READOUT_AMBIGUOUS_PENDING = "GEN_STOP_READOUT_AMBIGUOUS_PENDING"
    GEN_STOP_READOUT_UNAVAILABLE = "GEN_STOP_READOUT_UNAVAILABLE"
    GEN_STOP_STALE_ASSEMBLY = "GEN_STOP_STALE_ASSEMBLY"
    GEN_STOP_EMPTY_FRONTIER = "GEN_STOP_EMPTY_FRONTIER"
    GEN_STOP_LOOP_DETECTED = "GEN_STOP_LOOP_DETECTED"
    GEN_STOP_MAX_LEN = "GEN_STOP_MAX_LEN"
    GEN_STOP_CONTEXT_INVALID = "GEN_STOP_CONTEXT_INVALID"


class DGCAError(Exception):
    """Base exception for all normative DGCA v2 errors."""

    def __init__(self, code: StatusCode | str, message: str = "") -> None:
        self.code = StatusCode(code) if not isinstance(code, StatusCode) else code
        self.message = message or str(self.code)
        super().__init__(f"[{self.code}] {self.message}")


class EncoderError(DGCAError):
    """Raised when the stateless mechanical Encoder rejects an input."""


class InvalidEncoderInputError(EncoderError):
    """Raised on invalid UTF-8, lone surrogates, or forbidden bytes."""

    def __init__(self, message: str = "", code: StatusCode = StatusCode.INVALID_ENCODER_INPUT) -> None:
        super().__init__(code, message)


class ReservedControlByteError(InvalidEncoderInputError):
    """Raised when caller input contains 0x00 or reserved control bytes 0x01..0x1F."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, code=StatusCode.RESERVED_CONTROL_BYTE)


class EmptyExposureInputError(EncoderError):
    """Raised when whitespace stripping yields an empty input string."""

    def __init__(self, message: str = "") -> None:
        super().__init__(StatusCode.EMPTY_EXPOSURE_INPUT, message)


class EmptyLexicalExposureError(EncoderError):
    """Raised when an exposure consists solely of terminal EOS delimiters."""

    def __init__(self, message: str = "") -> None:
        super().__init__(StatusCode.EMPTY_LEXICAL_EXPOSURE, message)


class TokenTooLongError(EncoderError):
    """Raised when a lexical token exceeds MAX_TOKEN_UTF8_BYTES (64 bytes)."""

    def __init__(self, message: str = "") -> None:
        super().__init__(StatusCode.TOKEN_TOO_LONG, message)


class ObservationError(DGCAError):
    """Raised when SIC-V1 or observation validation fails."""

    def __init__(self, message: str = "", code: StatusCode = StatusCode.INVALID_OBSERVATION) -> None:
        super().__init__(code, message)


class SerializationError(DGCAError):
    """Raised when binary serialization or schema validation fails."""

    def __init__(self, message: str = "", code: StatusCode = StatusCode.INVALID_SERIALIZATION) -> None:
        super().__init__(code, message)
