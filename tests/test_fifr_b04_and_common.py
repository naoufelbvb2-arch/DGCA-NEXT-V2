"""Unit tests for Phase 1 numeric primitives, serialization, and FIFR-B04 SIC-V1 vectors."""

from __future__ import annotations

import pytest

from dgca.common import (
    DGCAError,
    ObservationError,
    Region,
    Role,
    RoleV2Record,
    SerializationError,
    WitnessSourceKind,
    compute_fp_role_v1,
    compute_fp_role_v2,
    compute_owner_profile_v1_digest,
    compute_owner_profile_v2_digest,
    format_support_millionths,
    noisy_or_float64,
    noisy_or_millionths,
    pack_binary64_be,
    pack_record_envelope,
    parse_support_millionths,
    q6_from_binary64,
    sic_v1_project_feature,
    unpack_binary64_be,
    unpack_record_envelope,
)
from dgca.core import CellAddress, project_sic_v1


class TestFIFRB04ReferenceVectors:
    """Verify exact SHA-256 SIC-V1 reference vectors from DGCA_CORE_RC4_1.md §3.1."""

    def test_sic_v1_single_feature_vectors(self) -> None:
        # 1. "a"
        salt_a, sorted_a = sic_v1_project_feature(b"a", Region.LANGUAGE)
        assert list(salt_a) == [1153, 3989, 414, 3603]
        assert list(sorted_a) == [414, 1153, 3603, 3989]

        # 2. "ab"
        salt_ab, sorted_ab = sic_v1_project_feature(b"ab", Region.LANGUAGE)
        assert list(salt_ab) == [3449, 2321, 502, 2081]
        assert list(sorted_ab) == [502, 2081, 2321, 3449]

        # 3. "é" (precomposed U+00E9 and decomposed "e" + U+0301 via project_sic_v1)
        res_pre = project_sic_v1([("\u00e9", "1.000000")], region=Region.LANGUAGE)
        res_dec = project_sic_v1([("e\u0301", "1.000000")], region=Region.LANGUAGE)
        assert list(res_pre.feature_details[0].salt_order_local_indices) == [1138, 1220, 3626, 1003]
        assert list(res_pre.feature_details[0].sorted_distinct_local_indices) == [1003, 1138, 1220, 3626]
        assert res_pre.feature_details == res_dec.feature_details
        assert res_pre.feature_bundle_digest == res_dec.feature_bundle_digest

        # 4. "f617"
        salt_f617, sorted_f617 = sic_v1_project_feature(b"f617", Region.LANGUAGE)
        assert list(salt_f617) == [414, 8, 1843, 2734]
        assert list(sorted_f617) == [8, 414, 1843, 2734]

    def test_shared_receiver_noisy_or_and_duplicate_feature_merge(self) -> None:
        # Core §3.1: With two distinct features a:0.500000, f617:0.250000, and salience 1.000000,
        # shared receiver global_id=8192+414=8606 MUST have X_fixed=625000, while a-only receivers
        # have 500000 and f617-only receivers 250000.
        res = project_sic_v1(
            [("a", "0.500000"), ("f617", "0.250000")],
            salience="1.000000",
            region=Region.LANGUAGE,
        )
        assert res.x_fixed_by_global_id[8606] == 625000
        assert res.aliased_global_cell_ids == (8606,)

        # a-only receivers: 8192 + {1153, 3603, 3989} = {9345, 11795, 12181}
        for gid in (9345, 11795, 12181):
            assert res.x_fixed_by_global_id[gid] == 500000

        # f617-only receivers: 8192 + {8, 1843, 2734} = {8200, 10035, 10926}
        for gid in (8200, 10035, 10926):
            assert res.x_fixed_by_global_id[gid] == 250000

        # Core §3.1: With a repeated 'a' input 0.500000 plus 0.250000, its four receivers
        # also have X_fixed=625000 (one merged feature, not two projection votes).
        res_rep = project_sic_v1(
            [("a", "0.500000"), ("a", "0.250000")],
            salience="1.000000",
            region=Region.LANGUAGE,
        )
        assert len(res_rep.feature_details) == 1
        assert res_rep.aliased_global_cell_ids == ()
        for gid in (8606, 9345, 11795, 12181):
            assert res_rep.x_fixed_by_global_id[gid] == 625000

    def test_fp_role_v1_reference_digest(self) -> None:
        # Core §3.1: For role=P and feature a:0.500000, the ascending global IDs
        # [8606,9345,11795,12181] with 500000 each MUST give digest:
        # 6cce77c3fc8da8bed4973ec695b267c3430807001563606989f40a3fe383b337
        res = project_sic_v1([("a", "0.500000")], salience="1.000000", region=Region.LANGUAGE)
        assert res.sorted_direct_items == (
            (8606, 500000),
            (9345, 500000),
            (11795, 500000),
            (12181, 500000),
        )
        digest_hex = res.role_fingerprint_v1(Role.P).hex()
        assert digest_hex == "6cce77c3fc8da8bed4973ec695b267c3430807001563606989f40a3fe383b337"


class TestCommonNumericAndSerialization:
    """Test numeric validation, Q6 quantization, cell addressing, and big-endian serialization."""

    def test_support_parsing_and_validation(self) -> None:
        assert parse_support_millionths("0") == 0
        assert parse_support_millionths("0.000000") == 0
        assert parse_support_millionths("1") == 1_000_000
        assert parse_support_millionths("1.0") == 1_000_000
        assert parse_support_millionths("1.000000") == 1_000_000
        assert parse_support_millionths("0.5") == 500_000
        assert parse_support_millionths("0.750000") == 750_000
        assert format_support_millionths(750_000) == "0.750000"
        assert format_support_millionths(1_000_000) == "1.000000"

        for invalid in ["", "-0.5", "+0.5", "1.0000001", "0.1234567", "1e-5", "NaN", "Inf", "-0", "1.5"]:
            with pytest.raises(ObservationError):
                parse_support_millionths(invalid)

    def test_noisy_or_half_even_rounding(self) -> None:
        # Test exact tie-to-even:
        # If u1 = 500_000 (0.5) and u2 = 1 (0.000001):
        # 1 - 0.5 * 0.999999 = 0.5000005 -> 500000.5 millionths -> rounds to even 500_000
        assert noisy_or_millionths([500_000, 1]) == 500_000
        # If u1 = 500_000 (0.5) and u2 = 3 (0.000003):
        # 1 - 0.5 * 0.999997 = 0.5000015 -> 500001.5 millionths -> rounds to even 500_002
        assert noisy_or_millionths([500_000, 3]) == 500_002

    def test_q6_from_binary64_and_noisy_or_float64(self) -> None:
        assert q6_from_binary64(0.25) == 250_000
        assert q6_from_binary64(0.80) == 800_000
        assert q6_from_binary64(-0.0) == 0
        assert noisy_or_float64([0.5, 0.25]) == 0.625

        with pytest.raises(DGCAError):
            q6_from_binary64(float("nan"))
        with pytest.raises(DGCAError):
            q6_from_binary64(float("inf"))

    def test_cell_address_bijection(self) -> None:
        addr = CellAddress.from_global_id(8606)
        assert addr.region == Region.LANGUAGE
        assert addr.local_index == 414
        assert addr.microcolumn_index == 414 // 8
        assert addr.mc_row == (414 // 8) // 16
        assert addr.mc_col == (414 // 8) % 16
        assert addr.slot == 414 % 8

        addr2 = CellAddress.from_coordinates(addr.region, addr.mc_row, addr.mc_col, addr.slot)
        assert addr2 == addr

    def test_binary64_and_record_serialization(self) -> None:
        # -0.0 must normalize to +0.0 canonical 8 zero bytes
        packed_neg_zero = pack_binary64_be(-0.0)
        assert packed_neg_zero == b"\x00" * 8
        val, next_off = unpack_binary64_be(packed_neg_zero)
        assert val == 0.0 and next_off == 8

        # Record envelope roundtrip
        env = pack_record_envelope(0x10, 0x02, b"test-payload")
        tag, ver, payload, end_off = unpack_record_envelope(env)
        assert (tag, ver, payload, end_off) == (0x10, 0x02, b"test-payload", len(env))

        with pytest.raises(SerializationError):
            pack_binary64_be(float("nan"))

    def test_fp_role_v2_and_owner_profile_digests(self) -> None:
        p_v1 = [(8606, 500_000)]
        c_v1 = [(9345, 800_000)]
        y_v1 = [(11795, 750_000)]
        d_v1 = compute_owner_profile_v1_digest(p_v1, c_v1, y_v1)
        assert len(d_v1) == 32

        p_v2 = [
            RoleV2Record(
                global_cell_id=8500,
                support_millionths=700_000,
                kind=WitnessSourceKind.DERIVED_EXTERNAL_CONTEXT,
                parent_anchor_global_cell_id=8200,
                parent_owner_counter=1,
                parent_binding_generation=2,
            ),
            RoleV2Record(
                global_cell_id=8606,
                support_millionths=500_000,
                kind=WitnessSourceKind.DIRECT,
            ),
        ]
        c_v2 = [RoleV2Record(global_cell_id=9345, support_millionths=800_000)]
        y_v2 = [RoleV2Record(global_cell_id=11795, support_millionths=750_000)]
        role_v2_digest = compute_fp_role_v2(Role.P, p_v2)
        assert len(role_v2_digest) == 32
        d_v2 = compute_owner_profile_v2_digest(p_v2, c_v2, y_v2)
        assert len(d_v2) == 32
        assert d_v1 != d_v2
