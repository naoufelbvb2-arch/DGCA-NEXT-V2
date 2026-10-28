"""Deterministic SHA-256 domain-separated hashing and physical fingerprinting for DGCA v2.

Normative references:
- DGCA-DCR-ENCODER-SPEC §2.3 (DGCA-BUNDLE-V1)
- DGCA_CORE_RC4_1.md §3.1 (DGCA-SIC-V1, FP-ROLE-V1, DGCA-OWNER-PROFILE-V1)
- DGCA_LLA_RC4_1.md §6.6 (FP-ROLE-V2, DGCA-OWNER-PROFILE-V2)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
import hashlib
import struct

from dgca.common.errors import DGCAError, ObservationError, StatusCode
from dgca.common.numeric import MILLION


class Region(IntEnum):
    """Canonical region byte identifiers (Core §1.1, §3.1)."""

    VISION = 0x00
    AUDIO = 0x01
    LANGUAGE = 0x02


class Role(IntEnum):
    """Canonical contextual role byte identifiers (Core §3.1, §7.4)."""

    P = 0x00
    C = 0x01
    Y = 0x02


class WitnessSourceKind(IntEnum):
    """Canonical witness source kind byte for FP-ROLE-V2 (LLA §6.6)."""

    DIRECT = 0x00
    DERIVED_EXTERNAL_CONTEXT = 0x01


REGION_CELL_COUNT: int = 4096
TOTAL_CELL_COUNT: int = 12288

# Core §3.1 fixed 16-byte salts (k = 0, 1, 2, 3)
SIC_SALTS: tuple[bytes, bytes, bytes, bytes] = (
    bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
    bytes.fromhex("101112131415161718191a1b1c1d1e1f"),
    bytes.fromhex("202122232425262728292a2b2c2d2e2f"),
    bytes.fromhex("303132333435363738393a3b3c3d3e3f"),
)

DOMAIN_SIC_V1: bytes = b"DGCA-SIC-V1\x00"
DOMAIN_BUNDLE_V1: bytes = b"DGCA-BUNDLE-V1\x00"
DOMAIN_ROLE_V1: bytes = b"DGCA-ROLE-V1\x00"
DOMAIN_ROLE_V2: bytes = b"DGCA-ROLE-V2\x00"
DOMAIN_OWNER_PROFILE_V1: bytes = b"DGCA-OWNER-PROFILE-V1\x00"
DOMAIN_OWNER_PROFILE_V2: bytes = b"DGCA-OWNER-PROFILE-V2\x00"


def sha256_bytes(data: bytes) -> bytes:
    """Compute standard 32-byte SHA-256 digest."""
    return hashlib.sha256(data).digest()


def sic_v1_project_feature_salt(
    normalized_feature_utf8: bytes,
    region: Region | int,
    salt_index: int,
) -> int:
    """Compute the region-local cell index in [0, 4095] for one feature and one salt index k in 0..3.

    Core §3.1:
    payload = ASCII("DGCA-SIC-V1") || 0x00 || region_u8 || salt_index_u8 || salt_16
              || feature_length_u32_BE || normalized_feature_UTF8
    Interpret first 8 digest bytes of SHA256(payload) as unsigned big-endian uint64,
    reduce modulo 4096.
    """
    region_u8 = int(Region(region))
    if salt_index < 0 or salt_index >= 4:
        raise DGCAError(StatusCode.INVALID_OBSERVATION, f"Invalid salt_index: {salt_index}")
    if not normalized_feature_utf8 or len(normalized_feature_utf8) > 4096:
        raise ObservationError(
            f"Normalized feature UTF-8 length {len(normalized_feature_utf8)} outside [1, 4096]"
        )

    salt_16 = SIC_SALTS[salt_index]
    header = struct.pack(">BB16sI", region_u8, salt_index, salt_16, len(normalized_feature_utf8))
    payload = DOMAIN_SIC_V1 + header + normalized_feature_utf8
    digest = hashlib.sha256(payload).digest()
    first_u64 = struct.unpack(">Q", digest[:8])[0]
    return int(first_u64 % REGION_CELL_COUNT)


def sic_v1_project_feature(
    normalized_feature_utf8: bytes,
    region: Region | int = Region.LANGUAGE,
) -> tuple[tuple[int, int, int, int], tuple[int, ...]]:
    """Project a normalized UTF-8 feature across all 4 salts.

    Returns:
        (salt_order_local_indices, sorted_distinct_local_indices)
    """
    region_enum = Region(region)
    salt_indices = (
        sic_v1_project_feature_salt(normalized_feature_utf8, region_enum, 0),
        sic_v1_project_feature_salt(normalized_feature_utf8, region_enum, 1),
        sic_v1_project_feature_salt(normalized_feature_utf8, region_enum, 2),
        sic_v1_project_feature_salt(normalized_feature_utf8, region_enum, 3),
    )
    sorted_distinct = tuple(sorted(set(salt_indices)))
    return salt_indices, sorted_distinct


def serialize_feature_bundle_v1(
    salience_u: int,
    sorted_features: Sequence[tuple[bytes, int]],
) -> bytes:
    """Serialize canonical feature bundle payload for DGCA-BUNDLE-V1 (Encoder §2.3).

    Format:
    ASCII("DGCA-BUNDLE-V1") || 0x00 || salience_millionths_u32_BE || feature_count_u32_BE
    || for each sorted feature: (byte_length_u32_BE || feature_UTF8_bytes || support_millionths_u32_BE)
    """
    if salience_u < 0 or salience_u > MILLION:
        raise ObservationError(f"Salience millionths out of range: {salience_u}")

    parts: list[bytes] = [
        DOMAIN_BUNDLE_V1,
        struct.pack(">II", salience_u, len(sorted_features)),
    ]
    prev_bytes: bytes | None = None
    for feat_bytes, support_u in sorted_features:
        if not feat_bytes or len(feat_bytes) > 4096:
            raise ObservationError(f"Invalid feature byte length: {len(feat_bytes)}")
        if prev_bytes is not None and feat_bytes <= prev_bytes:
            raise ObservationError(
                "Features in DGCA-BUNDLE-V1 must be strictly sorted in ascending unsigned UTF-8 byte order"
            )
        if support_u < 0 or support_u > MILLION:
            raise ObservationError(f"Support millionths out of range: {support_u}")
        prev_bytes = feat_bytes
        parts.append(struct.pack(">I", len(feat_bytes)))
        parts.append(feat_bytes)
        parts.append(struct.pack(">I", support_u))

    return b"".join(parts)


def compute_feature_bundle_digest(
    salience_u: int,
    sorted_features: Sequence[tuple[bytes, int]],
) -> bytes:
    """Compute the 32-byte SHA-256 digest of a canonical DGCA-BUNDLE-V1 feature bundle."""
    return sha256_bytes(serialize_feature_bundle_v1(salience_u, sorted_features))


def serialize_fp_role_v1(
    role: Role | int,
    items: Sequence[tuple[int, int]],
) -> bytes:
    """Serialize canonical FP-ROLE-V1 payload (Core §3.1).

    Format:
    ASCII("DGCA-ROLE-V1") || 0x00 || role_u8 || item_count_u32_BE || items
    where each item is global_cell_id_u32_BE || direct_support_millionths_u32_BE,
    with unique IDs strictly sorted ascending and no zero supports.
    """
    role_u8 = int(Role(role))
    parts: list[bytes] = [
        DOMAIN_ROLE_V1,
        struct.pack(">BI", role_u8, len(items)),
    ]
    prev_cell_id = -1
    for global_cell_id, support_u in items:
        if global_cell_id < 0 or global_cell_id >= TOTAL_CELL_COUNT:
            raise ObservationError(f"Global cell ID out of bounds: {global_cell_id}")
        if global_cell_id <= prev_cell_id:
            raise ObservationError(
                f"FP-ROLE-V1 items must have strictly ascending unique global_cell_id (got {global_cell_id} after {prev_cell_id})"
            )
        if support_u <= 0 or support_u > MILLION:
            raise ObservationError(
                f"FP-ROLE-V1 requires positive support millionths in (0, 1_000_000], got {support_u}"
            )
        prev_cell_id = global_cell_id
        parts.append(struct.pack(">II", global_cell_id, support_u))

    return b"".join(parts)


def compute_fp_role_v1(
    role: Role | int,
    items: Sequence[tuple[int, int]],
) -> bytes:
    """Compute the 32-byte SHA-256 digest for FP-ROLE-V1 (Core §3.1)."""
    return sha256_bytes(serialize_fp_role_v1(role, items))


@dataclass(frozen=True, slots=True)
class RoleV2Record:
    """Single item record for FP-ROLE-V2 (LLA §6.6)."""

    global_cell_id: int
    support_millionths: int
    kind: WitnessSourceKind = WitnessSourceKind.DIRECT
    parent_anchor_global_cell_id: int = 0
    parent_owner_counter: int = 0
    parent_binding_generation: int = 0


def serialize_fp_role_v2(
    role: Role | int,
    records: Sequence[RoleV2Record],
) -> bytes:
    """Serialize canonical FP-ROLE-V2 payload (LLA §6.6).

    Format:
    ASCII("DGCA-ROLE-V2") || 0x00 || role_u8 || item_count_u32_BE || records sorted cell_id ascending
    record = global_cell_id_u32_BE || support_millionths_u32_BE
           || kind_u8 (DIRECT=0, DERIVED_EXTERNAL_CONTEXT=1)
           || parent_anchor_global_cell_id_u32_BE (0 for DIRECT)
           || parent_owner_counter_u64_BE (0 for DIRECT)
           || parent_binding_generation_u32_BE (0 for DIRECT)
    """
    role_enum = Role(role)
    parts: list[bytes] = [
        DOMAIN_ROLE_V2,
        struct.pack(">BI", int(role_enum), len(records)),
    ]
    prev_cell_id = -1
    for rec in records:
        if rec.global_cell_id < 0 or rec.global_cell_id >= TOTAL_CELL_COUNT:
            raise ObservationError(f"Global cell ID out of bounds: {rec.global_cell_id}")
        if rec.global_cell_id <= prev_cell_id:
            raise ObservationError(
                "FP-ROLE-V2 records must have strictly ascending unique global_cell_id"
            )
        if rec.support_millionths <= 0 or rec.support_millionths > MILLION:
            raise ObservationError(
                f"FP-ROLE-V2 requires positive support millionths, got {rec.support_millionths}"
            )
        kind_enum = WitnessSourceKind(rec.kind)
        if role_enum in (Role.C, Role.Y) and kind_enum != WitnessSourceKind.DIRECT:
            raise ObservationError(
                f"Role {role_enum.name} only permits DIRECT observations in FP-ROLE-V2"
            )
        if kind_enum == WitnessSourceKind.DIRECT:
            if (
                rec.parent_anchor_global_cell_id != 0
                or rec.parent_owner_counter != 0
                or rec.parent_binding_generation != 0
            ):
                raise ObservationError("DIRECT source parent fields must all be 0 in FP-ROLE-V2")
        else:
            if rec.parent_owner_counter <= 0 or rec.parent_binding_generation <= 0:
                raise ObservationError(
                    "DERIVED_EXTERNAL_CONTEXT source must have positive parent owner counter and generation"
                )
        prev_cell_id = rec.global_cell_id
        parts.append(
            struct.pack(
                ">IIB I Q I",
                rec.global_cell_id,
                rec.support_millionths,
                int(kind_enum),
                rec.parent_anchor_global_cell_id,
                rec.parent_owner_counter,
                rec.parent_binding_generation,
            )
        )
    return b"".join(parts)


def compute_fp_role_v2(
    role: Role | int,
    records: Sequence[RoleV2Record],
) -> bytes:
    """Compute the 32-byte SHA-256 digest for FP-ROLE-V2 (LLA §6.6)."""
    return sha256_bytes(serialize_fp_role_v2(role, records))


def compute_owner_profile_v1_digest(
    p_items: Sequence[tuple[int, int]],
    c_items: Sequence[tuple[int, int]],
    y_items: Sequence[tuple[int, int]],
) -> bytes:
    """Compute DGCA-OWNER-PROFILE-V1 digest over fixed (P, C, Y) role subrecords (Core §3.1)."""
    p_sub = serialize_fp_role_v1(Role.P, p_items)
    c_sub = serialize_fp_role_v1(Role.C, c_items)
    y_sub = serialize_fp_role_v1(Role.Y, y_items)
    payload = (
        DOMAIN_OWNER_PROFILE_V1
        + struct.pack(">I", len(p_sub))
        + p_sub
        + struct.pack(">I", len(c_sub))
        + c_sub
        + struct.pack(">I", len(y_sub))
        + y_sub
    )
    return sha256_bytes(payload)


def compute_owner_profile_v2_digest(
    p_records: Sequence[RoleV2Record],
    c_records: Sequence[RoleV2Record],
    y_records: Sequence[RoleV2Record],
) -> bytes:
    """Compute DGCA-OWNER-PROFILE-V2 digest over fixed (P, C, Y) role v2 subrecords (LLA §6.6)."""
    p_sub = serialize_fp_role_v2(Role.P, p_records)
    c_sub = serialize_fp_role_v2(Role.C, c_records)
    y_sub = serialize_fp_role_v2(Role.Y, y_records)
    payload = (
        DOMAIN_OWNER_PROFILE_V2
        + struct.pack(">I", len(p_sub))
        + p_sub
        + struct.pack(">I", len(c_sub))
        + c_sub
        + struct.pack(">I", len(y_sub))
        + y_sub
    )
    return sha256_bytes(payload)
