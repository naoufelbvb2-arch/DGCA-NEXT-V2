"""Mandatory Encoder validation gates (ENC-T01 to ENC-T10) and §5.1 reference vectors.

Normative references:
- DGCA-DCR-ENCODER-SPEC §5.1 (Canonical decomposition and SIC-V1 projection reference vectors)
- DGCA-DCR-ENCODER-SPEC §5.2 (Mandatory Encoder test gates ENC-T01 to ENC-T10)
"""

from __future__ import annotations

import pytest

from dgca.common import (
    EmptyExposureInputError,
    EmptyLexicalExposureError,
    InvalidEncoderInputError,
    Region,
    ReservedControlByteError,
    Role,
    StatusCode,
    TokenTooLongError,
)
from dgca.core import (
    compute_weighted_footprint_distance,
    project_core_event_v1,
    project_sic_v1,
    simulate_cold_language_event,
)
from dgca.encoder import (
    EOS_RAW_SURFACE,
    EventOrigin,
    Marker,
    decompose_eos_event,
    decompose_lexical_token,
    encode_exposure,
    encode_lexical_token_event,
    reinject_attested_bundle,
)


class TestEncoderReferenceVectorsSection5_1:
    """Verify exact decomposition and byte ordering from DGCA-DCR-ENCODER-SPEC §5.1."""

    def test_vector_1_single_char_a(self) -> None:
        features = decompose_lexical_token("a")
        assert features == (
            ("1$:a", "0.800000"),
            ("^1:a", "0.900000"),
            ("^a$", "1.000000"),
        )
        assert [f.encode("utf-8").hex() for f, _ in features] == [
            "31243a61",
            "5e313a61",
            "5e6124",
        ]

    def test_vector_2_two_char_ab(self) -> None:
        features = decompose_lexical_token("ab")
        assert features == (
            ("^ab", "0.900000"),
            ("^ab$", "1.000000"),
            ("ab$", "0.800000"),
        )
        assert [f.encode("utf-8").hex() for f, _ in features] == [
            "5e6162",
            "5e616224",
            "616224",
        ]

    def test_vector_3_three_char_arabic_kataba(self) -> None:
        features = decompose_lexical_token("كتب")
        assert features == (
            ("^كت", "0.900000"),
            ("^كتب$", "1.000000"),
            ("~كتب", "0.750000"),
            ("تب$", "0.800000"),
        )
        assert [f.encode("utf-8").hex() for f, _ in features] == [
            "5ed983d8aa",
            "5ed983d8aad8a824",
            "7ed983d8aad8a8",
            "d8aad8a824",
        ]

    def test_vector_4_canonical_eos(self) -> None:
        features = decompose_eos_event()
        assert features == (
            ("\x1fEOS#0", "1.000000"),
            ("\x1fEOS#1", "0.900000"),
            ("\x1fEOS#2", "0.800000"),
        )
        assert [f.encode("utf-8").hex() for f, _ in features] == [
            "1f454f532330",
            "1f454f532331",
            "1f454f532332",
        ]


class TestMandatoryEncoderGatesSection5_2:
    """Execute mandatory Encoder validation gates ENC-T01 through ENC-T10."""

    def test_enc_t01_nfc_normalization_equivalence(self) -> None:
        """ENC-T01: Decomposed 'e\\u0301' vs precomposed '\\u00e9'."""
        env_dec = encode_lexical_token_event("e\u0301")
        env_pre = encode_lexical_token_event("\u00e9")

        assert env_dec.peripheral_surface.raw_surface_nfc_utf8 == "\u00e9"
        assert env_pre.peripheral_surface.raw_surface_nfc_utf8 == "\u00e9"
        # Sorted by unsigned UTF-8 byte order: '1' (0x31) < '^1' (0x5e 0x31) < '^é' (0x5e 0xc3 0xa9)
        expected_features = (
            ("1$:é", "0.800000"),
            ("^1:é", "0.900000"),
            ("^é$", "1.000000"),
        )
        assert env_dec.core_event.features == expected_features
        assert env_pre.core_event.features == expected_features
        assert env_dec.core_event.feature_bundle_digest == env_pre.core_event.feature_bundle_digest
        assert env_dec.peripheral_surface.surface_sha256 == env_pre.peripheral_surface.surface_sha256

    def test_enc_t02_feature_count_and_cell_capacity_bounds(self) -> None:
        """ENC-T02: Any lexical token w with 1 <= L <= 30 emits 3 or 4 features and [3, 16] LANGUAGE cells."""
        for length in range(1, 31):
            token = "".join(chr(ord("a") + (i % 26)) for i in range(length))
            env = encode_lexical_token_event(token)
            feat_count = len(env.core_event.features)
            if length in (1, 2):
                assert feat_count == 3
            else:
                assert feat_count == 4

            proj = project_core_event_v1(env.core_event)
            num_cells = len(proj.x_fixed_by_global_id)
            assert 3 <= num_cells <= 16
            for gid in proj.x_fixed_by_global_id:
                assert 8192 <= gid <= 12287

    def test_enc_t03_minimal_pair_arabic_contrast(self) -> None:
        """ENC-T03: Minimal pair 'كتب' vs 'كسب' has zero shared features and d(U, V) >= 0.80 >> 0.40."""
        env1 = encode_lexical_token_event("كتب")
        env2 = encode_lexical_token_event("كسب")

        feats1 = {f for f, _ in env1.core_event.features}
        feats2 = {f for f, _ in env2.core_event.features}
        assert len(feats1 & feats2) == 0

        proj1 = project_core_event_v1(env1.core_event)
        proj2 = project_core_event_v1(env2.core_event)
        dist = compute_weighted_footprint_distance(
            proj1.x_fixed_by_global_id, proj2.x_fixed_by_global_id
        )
        assert dist >= 0.80

    def test_enc_t04_anagram_pair_separation(self) -> None:
        """ENC-T04: Anagram pair 'حلم' vs 'ملح' has zero shared features and complete separation."""
        env1 = encode_lexical_token_event("حلم")
        env2 = encode_lexical_token_event("ملح")

        feats1 = {f for f, _ in env1.core_event.features}
        feats2 = {f for f, _ in env2.core_event.features}
        assert len(feats1 & feats2) == 0

        proj1 = project_core_event_v1(env1.core_event)
        proj2 = project_core_event_v1(env2.core_event)
        dist = compute_weighted_footprint_distance(
            proj1.x_fixed_by_global_id, proj2.x_fixed_by_global_id
        )
        assert dist >= 0.80

    def test_enc_t05_sentence_segmentation_and_single_eos(self) -> None:
        """ENC-T05: Sentence 'A B C.' with append_eos=true emits 4 events with no duplicate EOS."""
        envelopes = encode_exposure("A B C.", exposure_id=1, append_eos=True)
        assert len(envelopes) == 4

        assert envelopes[0].peripheral_surface.raw_surface_nfc_utf8 == "A"
        assert envelopes[0].core_event.boundary is True
        assert envelopes[0].peripheral_surface.marker == Marker.NONE
        assert envelopes[0].core_event.event_order == 0

        assert envelopes[1].peripheral_surface.raw_surface_nfc_utf8 == "B"
        assert envelopes[1].core_event.boundary is False
        assert envelopes[1].peripheral_surface.marker == Marker.NONE
        assert envelopes[1].core_event.event_order == 1

        assert envelopes[2].peripheral_surface.raw_surface_nfc_utf8 == "C"
        assert envelopes[2].core_event.boundary is False
        assert envelopes[2].peripheral_surface.marker == Marker.NONE
        assert envelopes[2].core_event.event_order == 2

        assert envelopes[3].peripheral_surface.raw_surface_nfc_utf8 == EOS_RAW_SURFACE
        assert envelopes[3].core_event.boundary is False
        assert envelopes[3].peripheral_surface.marker == Marker.EOS
        assert envelopes[3].core_event.event_order == 3

        # Also test internal punctuation detaching
        envelopes_punct = encode_exposure("أهلاً، يا صديقي!", exposure_id=2, append_eos=True)
        surfaces = [e.peripheral_surface.raw_surface_nfc_utf8 for e in envelopes_punct]
        assert surfaces == ["أهلاً", "،", "يا", "صديقي", "<EOS>"]

    def test_enc_t06_reserved_control_byte_rejection(self) -> None:
        """ENC-T06: User string containing byte 0x1F or 0x00 is rejected immediately; cannot spoof EOS."""
        with pytest.raises(ReservedControlByteError) as exc_1f:
            encode_exposure("hello \x1fEOS#0 world")
        assert exc_1f.value.code == StatusCode.RESERVED_CONTROL_BYTE
        assert isinstance(exc_1f.value, InvalidEncoderInputError)

        with pytest.raises(ReservedControlByteError) as exc_00:
            encode_exposure("hello\x00world")
        assert exc_00.value.code == StatusCode.RESERVED_CONTROL_BYTE

        # Invalid UTF-8 bytes
        with pytest.raises(InvalidEncoderInputError) as exc_utf8:
            encode_exposure(b"\xff\xfeinvalid")
        assert exc_utf8.value.code == StatusCode.INVALID_ENCODER_INPUT

    def test_enc_t07_cold_pass1_pass2_activity_and_creation_gate(self) -> None:
        """ENC-T07: Cold Pass-1/Pass-2 simulation of any encoded token under LANGUAGE constants."""
        sample_tokens = ["a", "ab", "cat", "كتب", "كسب", "و", "في", "استقلالية", ","]
        for tok in sample_tokens:
            env = encode_lexical_token_event(tok)
            proj = project_core_event_v1(env.core_event)
            sim = simulate_cold_language_event(proj)

            # All projected cells must achieve A_j^(1) >= theta_emit = 0.23
            assert sim.min_a1 >= 0.23
            assert len(sim.e1_frontier_global_ids) == len(proj.x_fixed_by_global_id)
            # Pairwise A_i^+ * A_j^+ >= theta_create = 0.20 (and even >= 0.30 historical comparator)
            assert sim.min_pairwise_coactivity >= 0.20

    def test_enc_t08_raw_feature_pass_through(self) -> None:
        """ENC-T08: RAW_FEATURE_PASS_THROUGH with ('a', '0.500000') and ('f617', '0.250000')."""
        proj_both = project_sic_v1(
            [("a", "0.500000"), ("f617", "0.250000")],
            salience="1.000000",
            region=Region.LANGUAGE,
        )
        assert proj_both.x_fixed_by_global_id[8606] == 625000

        proj_a_only = project_sic_v1(
            [("a", "0.500000")],
            salience="1.000000",
            region=Region.LANGUAGE,
        )
        assert proj_a_only.role_fingerprint_v1(Role.P).hex().startswith("6cce77c3")

    def test_enc_t09_reinjection_of_attested_bundle(self) -> None:
        """ENC-T09: Re-injection of attested bundle from SurfaceReadoutLedgerV1 in GENERATE_EPISODE."""
        original_env = encode_lexical_token_event("كتب", exposure_id=10, event_order=2)
        orig_proj = project_core_event_v1(original_env.core_event)

        reinjected_core_event = reinject_attested_bundle(
            original_env.peripheral_surface,
            event_order=5,
            exposure_id=None,
        )
        assert reinjected_core_event.origin == EventOrigin.INTERNAL_SELECTED
        assert reinjected_core_event.boundary is False
        assert reinjected_core_event.feature_bundle_digest == original_env.core_event.feature_bundle_digest

        reinjected_proj = project_core_event_v1(reinjected_core_event)
        assert reinjected_proj.x_fixed_by_global_id == orig_proj.x_fixed_by_global_id
        assert reinjected_proj.x_float_by_global_id == orig_proj.x_float_by_global_id

    def test_enc_t10_token_too_long_and_empty_exposure_errors(self) -> None:
        """ENC-T10: Token with > 64 UTF-8 bytes or empty whitespace-only exposure."""
        with pytest.raises(TokenTooLongError) as exc_long:
            encode_lexical_token_event("a" * 65)
        assert exc_long.value.code == StatusCode.TOKEN_TOO_LONG

        # Exactly 64 bytes is allowed
        env_64 = encode_lexical_token_event("a" * 64)
        assert len(env_64.core_event.features) == 4

        # Empty or whitespace-only exposure
        for empty_str in ["", "   ", "\t\n\r  "]:
            with pytest.raises(EmptyExposureInputError) as exc_empty:
                encode_exposure(empty_str)
            assert exc_empty.value.code == StatusCode.EMPTY_EXPOSURE_INPUT

        # Bare EOS exposure
        with pytest.raises(EmptyLexicalExposureError) as exc_bare_eos:
            encode_exposure("...")
        assert exc_bare_eos.value.code == StatusCode.EMPTY_LEXICAL_EXPOSURE
