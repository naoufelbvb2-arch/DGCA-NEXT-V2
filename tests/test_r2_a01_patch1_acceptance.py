"""Acceptance test suite for R2-A01 Patch 1: Surface Provenance & Exact Event Identity.

Covers:
- Acceptance scenarios P2-01 through P2-09 (Provenance, surface verification, canonical EOS)
- Acceptance scenarios P3-01 through P3-06 (Event identity, idempotency, retry collision detection)
- Focused edge cases (salience variations, modality changes, literal <EOS>, Unicode NFC, zero-bleed rejection)
"""

from __future__ import annotations

import dataclasses
import hashlib
import unicodedata
import pytest

from dgca.common.errors import DGCAError, ObservationError, StatusCode
from dgca.common.hashing import Region, sha256_bytes
from dgca.core.dynamics import EventExecutionResult
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import Assembly, AssemblyStatus, MachineState
from dgca.encoder.decomposer import (
    EOS_CANONICAL_FEATURES,
    decompose_lexical_token,
    finalize_feature_bundle,
)
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_exposure,
    encode_lexical_token_event,
)
from dgca.lifecycle.exposure_tx import (
    CanonicalEnvelopeIdentity,
    EventIdentityKey,
    ExposureStatus,
    ExposureTransactionManager,
    validate_event_envelope_provenance,
)
from dgca.lla.witness import ObservationScope
from dgca.peripheral.outbox import build_end_exposure_outbox_notifications


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lexical_pair(
    surface: str,
    *,
    root_id: int = 1,
    event_order: int = 0,
    boundary: bool = True,
    salience: str = "1.000000",
    modality: Region = Region.LANGUAGE,
) -> tuple[CoreEventPayloadV1, PeripheralSurfaceEnvelopeV1]:
    encoded = encode_lexical_token_event(
        surface,
        exposure_id=root_id,
        event_order=event_order,
        boundary=boundary,
        salience=salience,
    )
    core = encoded.core_event
    if modality != Region.LANGUAGE:
        core = dataclasses.replace(core, modality=modality)
    return core, encoded.peripheral_surface


def _make_canonical_eos_pair(
    *,
    root_id: int = 1,
    event_order: int = 1,
    salience: str = "1.000000",
) -> tuple[CoreEventPayloadV1, PeripheralSurfaceEnvelopeV1]:
    canonical_features, _, salience_u, digest = finalize_feature_bundle(
        EOS_CANONICAL_FEATURES,
        salience=salience,
        allow_reserved_control=True,
    )
    surface = "<EOS>"
    surf_hash = hashlib.sha256(surface.encode("utf-8")).digest()
    core = CoreEventPayloadV1(
        exposure_id=root_id,
        event_order=event_order,
        modality=Region.LANGUAGE,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=False,
        salience=salience,
        features=canonical_features,
        feature_bundle_digest=digest,
    )
    env = PeripheralSurfaceEnvelopeV1(
        raw_surface_nfc_utf8=surface,
        surface_sha256=surf_hash,
        feature_bundle_digest=digest,
        canonical_features_copy=canonical_features,
        marker=Marker.EOS,
    )
    return core, env


# ---------------------------------------------------------------------------
# Section P2: Provenance & Canonical EOS Tests (P2-01 to P2-09)
# ---------------------------------------------------------------------------

class TestPatch1ProvenanceAndEOS:
    """Acceptance scenarios P2-01 through P2-09."""

    def test_p2_01_canonical_lexical_provenance_acceptance(self) -> None:
        """P2-01: Canonical matching lexical event and envelope are accepted."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_ev, env = _make_lexical_pair("القط", root_id=1, event_order=0)
        res = tx.process_event(core_ev, peripheral_envelope=env)

        assert res.event_order == 0
        assert res.feature_bundle_digest == env.feature_bundle_digest
        assert tx.open_journal is not None
        assert 0 in tx.open_journal.peripheral_envelopes_by_order
        assert tx.open_journal.peripheral_envelopes_by_order[0] == env
        assert tx.open_journal.event_identities[0].envelope_identity is not None
        assert tx.open_journal.event_identities[0].envelope_identity.marker == Marker.NONE

    def test_p2_02_canonical_eos_acceptance(self) -> None:
        """P2-02: Canonical EOS accepted at event_order > 0 with boundary=False and Marker.EOS."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        core_eos, env_eos = _make_canonical_eos_pair(root_id=1, event_order=1)
        res_eos = tx.process_event(core_eos, peripheral_envelope=env_eos)

        assert res_eos.event_order == 1
        assert res_eos.feature_bundle_digest == env_eos.feature_bundle_digest
        assert tx.open_journal.event_identities[1].envelope_identity.marker == Marker.EOS

    def test_p2_03_digest_mismatch_rejection(self) -> None:
        """P2-03: Envelope with corrupted digest is rejected fast with PROVENANCE_DIGEST_MISMATCH."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_ev, env = _make_lexical_pair("القط", root_id=1, event_order=0)
        corrupted_env = dataclasses.replace(env, feature_bundle_digest=b"\x00" * 32)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_ev, peripheral_envelope=corrupted_env)
        assert exc_info.value.code == StatusCode.PROVENANCE_DIGEST_MISMATCH

        # Verify zero state changes
        assert tx.open_journal.next_event_order == 0
        assert len(tx.open_journal.event_results) == 0
        assert len(tx.open_journal.staged_proposals) == 0

    def test_p2_04_marker_mismatch_rejection(self) -> None:
        """P2-04: Lexical event with Marker.EOS or EOS with Marker.NONE raises PROVENANCE_MARKER_MISMATCH."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_ev, env = _make_lexical_pair("القط", root_id=1, event_order=0)
        corrupted_env = dataclasses.replace(env, marker=Marker.EOS)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_ev, peripheral_envelope=corrupted_env)
        assert exc_info.value.code == StatusCode.PROVENANCE_MARKER_MISMATCH

    def test_p2_05_surface_hash_inconsistency_rejection(self) -> None:
        """P2-05: Envelope surface_sha256 differing from sha256(raw_surface) is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_ev, env = _make_lexical_pair("القط", root_id=1, event_order=0)
        corrupted_env = dataclasses.replace(env, surface_sha256=b"\xff" * 32)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_ev, peripheral_envelope=corrupted_env)
        assert exc_info.value.code == StatusCode.INVALID_SURFACE_HASH
        assert tx.open_journal.next_event_order == 0

    def test_p2_06_canonical_feature_copy_mismatch(self) -> None:
        """P2-06: Envelope canonical feature copy differing from core features is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_ev, env = _make_lexical_pair("القط", root_id=1, event_order=0)
        corrupted_features = (("^tampered$", "1.000000"),)
        corrupted_env = dataclasses.replace(env, canonical_features_copy=corrupted_features)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_ev, peripheral_envelope=corrupted_env)
        assert exc_info.value.code == StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH

    def test_p2_07_eos_at_event_order_0_rejection(self) -> None:
        """P2-07: Canonical EOS presented as first event (event_order 0) is rejected as empty exposure."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_eos, env_eos = _make_canonical_eos_pair(root_id=1, event_order=0)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_eos, peripheral_envelope=env_eos)
        assert exc_info.value.code == StatusCode.EMPTY_LEXICAL_EXPOSURE
        assert tx.open_journal.next_event_order == 0

    def test_p2_08_surface_to_feature_tampering_rejection(self) -> None:
        """P2-08: Attacker replaces surface ('ماء' instead of 'حليب'), recomputes surface hash, but keeps features.
        
        Mechanical derivation directly from 'ماء' produces features of 'ماء', which fail match with 'حليب'.
        """
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_milk, env_milk = _make_lexical_pair("حليب", root_id=1, event_order=0)

        # Attacker crafts envelope with surface "ماء", recomputed hash, but leaves milk features/digest
        spoofed_surface = "ماء"
        spoofed_hash = hashlib.sha256(spoofed_surface.encode("utf-8")).digest()
        tampered_env = dataclasses.replace(
            env_milk,
            raw_surface_nfc_utf8=spoofed_surface,
            surface_sha256=spoofed_hash,
        )

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_milk, peripheral_envelope=tampered_env)
        assert exc_info.value.code == StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH
        assert tx.open_journal.next_event_order == 0

    def test_p2_09_strict_headless_rejection(self) -> None:
        """P2-09: Missing peripheral envelope in strict production mode raises PROVENANCE_ENVELOPE_MISSING."""
        state = MachineState()
        tx = ExposureTransactionManager(state, allow_headless_events=False)
        tx.begin_exposure(1)

        core_ev, _ = _make_lexical_pair("القط", root_id=1, event_order=0)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_ev, peripheral_envelope=None)
        assert exc_info.value.code == StatusCode.PROVENANCE_ENVELOPE_MISSING
        assert tx.open_journal.next_event_order == 0


# ---------------------------------------------------------------------------
# Section P3: Event Identity & Retry Collisions (P3-01 to P3-06)
# ---------------------------------------------------------------------------

class TestPatch1EventIdentityAndRetries:
    """Acceptance scenarios P3-01 through P3-06."""

    def test_p3_01_exact_idempotent_event_replay(self) -> None:
        """P3-01: Replaying identical event and envelope returns cached result without re-execution."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        res1 = tx.process_event(core0, peripheral_envelope=env0)

        proposals_after_res1 = len(tx.open_journal.staged_proposals)
        clock_after_res1 = state.W.global_event_clock

        # Re-send exact same event
        res2 = tx.process_event(core0, peripheral_envelope=env0)

        assert res1 is res2
        assert len(tx.open_journal.event_results) == 1
        assert len(tx.open_journal.staged_proposals) == proposals_after_res1
        assert state.W.global_event_clock == clock_after_res1

    def test_p3_02_core_payload_conflict_rejection(self) -> None:
        """P3-02: Retry of event 0 with altered core payload raises EVENT_RETRY_PAYLOAD_CONFLICT."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        # Alter boundary on retry
        conflicting_core = dataclasses.replace(core0, boundary=False)
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(conflicting_core, peripheral_envelope=env0)
        assert exc_info.value.code == StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT

    def test_p3_03_envelope_digest_conflict_rejection(self) -> None:
        """P3-03: Retry of event 0 with conflicting envelope digest is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        conflicting_env = dataclasses.replace(env0, feature_bundle_digest=b"\x11" * 32)
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core0, peripheral_envelope=conflicting_env)
        # Provenance validation catches digest mismatch on retry
        assert exc_info.value.code in (
            StatusCode.PROVENANCE_DIGEST_MISMATCH,
            StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT,
        )
        assert tx.open_journal.event_identities[0].envelope_identity.feature_bundle_digest == env0.feature_bundle_digest

    def test_p3_04_envelope_marker_conflict_rejection(self) -> None:
        """P3-04: Retry of event 0 with altered marker is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        conflicting_env = dataclasses.replace(env0, marker=Marker.EOS)
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core0, peripheral_envelope=conflicting_env)
        assert exc_info.value.code in (
            StatusCode.PROVENANCE_MARKER_MISMATCH,
            StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT,
        )

    def test_p3_05_envelope_feature_copy_conflict_rejection(self) -> None:
        """P3-05: Retry of event 0 with altered canonical feature copy is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        tampered_copy = (("^alt$", "1.000000"),)
        conflicting_env = dataclasses.replace(env0, canonical_features_copy=tampered_copy)
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core0, peripheral_envelope=conflicting_env)
        assert exc_info.value.code in (
            StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH,
            StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT,
        )

    def test_p3_06_retroactive_envelope_attachment_rejection(self) -> None:
        """P3-06: Headless event retry attempting retroactive envelope attachment is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state, allow_headless_events=True)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=None)

        # Retry with envelope attached
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core0, peripheral_envelope=env0)
        assert exc_info.value.code == StatusCode.EVENT_RETRY_PROVENANCE_ALTERATION
        assert 0 not in tx.open_journal.peripheral_envelopes_by_order


# ---------------------------------------------------------------------------
# Section Focused Cases: Modality, Salience, Literal <EOS>, NFC & Zero-Bleed
# ---------------------------------------------------------------------------

class TestPatch1FocusedEdgeCases:
    """Focused edge cases mandated by implementation authorization."""

    def test_changed_modality_on_retry_rejected(self) -> None:
        """Retry of event 0 with changed modality (LANGUAGE -> VISION) is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0, modality=Region.LANGUAGE)
        tx.process_event(core0, peripheral_envelope=env0)

        # Alter modality to VISION
        conflicting_core = dataclasses.replace(core0, modality=Region.VISION)
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(conflicting_core, peripheral_envelope=env0)
        assert exc_info.value.code == StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT

    def test_non_default_salience_acceptance_and_rejection(self) -> None:
        """Verify non-default salience (e.g. 0.500000) derives matching digest and verifies properly."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_sal, env_sal = _make_lexical_pair("القط", root_id=1, event_order=0, salience="0.500000")
        res = tx.process_event(core_sal, peripheral_envelope=env_sal)
        assert res.feature_bundle_digest == env_sal.feature_bundle_digest

        # A retry presenting default salience "1.000000" conflicts and is rejected
        core_default, env_default = _make_lexical_pair("القط", root_id=1, event_order=0, salience="1.000000")
        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_default, peripheral_envelope=env_default)
        assert exc_info.value.code == StatusCode.EVENT_RETRY_PAYLOAD_CONFLICT

    def test_literal_lexical_eos_token_accepted_with_marker_none(self) -> None:
        """Natural text '<EOS>' encoded as a literal lexical token (Marker.NONE) is valid and distinct from canonical EOS."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        # encode_lexical_token_event("<EOS>") uses Marker.NONE and lexical n-gram features
        encoded = encode_lexical_token_event("<EOS>", exposure_id=1, event_order=0)
        assert encoded.peripheral_surface.marker == Marker.NONE
        # Verify it has standard 4-feature orthographic decomposition, not reserved \x1f
        features = encoded.core_event.features
        assert any(f.startswith("^<EOS>$") for f, s in features)
        assert not any(f.startswith("\x1f") for f, s in features)

        res = tx.process_event(encoded.core_event, peripheral_envelope=encoded.peripheral_surface)
        assert res.event_order == 0
        assert tx.open_journal.event_identities[0].envelope_identity.marker == Marker.NONE

    def test_literal_lexical_eos_cannot_masquerade_as_canonical_eos(self) -> None:
        """Literal lexical '<EOS>' paired with Marker.EOS is rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        encoded = encode_lexical_token_event("<EOS>", exposure_id=1, event_order=0)
        masquerading_env = dataclasses.replace(encoded.peripheral_surface, marker=Marker.EOS)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(encoded.core_event, peripheral_envelope=masquerading_env)
        # Fails fast on event_order 0 EOS or feature mismatch
        assert exc_info.value.code in (
            StatusCode.EMPTY_LEXICAL_EXPOSURE,
            StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH,
            StatusCode.PROVENANCE_MARKER_MISMATCH,
        )

    def test_canonical_eos_cannot_be_replaced_by_lexical_features(self) -> None:
        """Envelope has Marker.EOS but core event has lexical features; rejected."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        # Event 1 with Marker.EOS envelope, but lexical features
        encoded_lex = encode_lexical_token_event("<EOS>", exposure_id=1, event_order=1, boundary=False)
        confused_env = dataclasses.replace(encoded_lex.peripheral_surface, marker=Marker.EOS)

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(encoded_lex.core_event, peripheral_envelope=confused_env)
        assert exc_info.value.code == StatusCode.PROVENANCE_FEATURE_COPY_MISMATCH

    def test_unicode_nfc_inconsistency_rejected(self) -> None:
        """Non-NFC normalized surface (decomposed 'e' + U+0301) is rejected fast."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core_ev, env = _make_lexical_pair("é", root_id=1, event_order=0)
        decomposed_surface = "e\u0301"  # NFD decomposed form
        assert not unicodedata.is_normalized("NFC", decomposed_surface)

        bad_nfc_env = dataclasses.replace(
            env,
            raw_surface_nfc_utf8=decomposed_surface,
            surface_sha256=hashlib.sha256(decomposed_surface.encode("utf-8")).digest(),
        )

        with pytest.raises(ObservationError) as exc_info:
            tx.process_event(core_ev, peripheral_envelope=bad_nfc_env)
        assert exc_info.value.code == StatusCode.INVALID_OBSERVATION

    def test_zero_state_changes_after_rejection(self) -> None:
        """Verify machine state and journal are byte-for-byte identical after a rejected event."""
        state = MachineState()
        tx = ExposureTransactionManager(state)
        tx.begin_exposure(1)

        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)
        tx.process_event(core0, peripheral_envelope=env0)

        # Snapshot journal and W
        pre_clock = state.W.global_event_clock
        pre_committed = dict(state.W.committed_cells)
        pre_proposals = list(tx.open_journal.staged_proposals)
        pre_results_len = len(tx.open_journal.event_results)

        # Submit corrupted event 1
        core1, env1 = _make_lexical_pair("يشرب", root_id=1, event_order=1)
        bad_env1 = dataclasses.replace(env1, surface_sha256=b"\x00" * 32)

        with pytest.raises(ObservationError):
            tx.process_event(core1, peripheral_envelope=bad_env1)

        # Assert zero side-effects
        assert state.W.global_event_clock == pre_clock
        assert state.W.committed_cells == pre_committed
        assert tx.open_journal.staged_proposals == pre_proposals
        assert len(tx.open_journal.event_results) == pre_results_len
        assert tx.open_journal.next_event_order == 1

    def test_outbox_explicit_digest_failure(self) -> None:
        """Verify build_end_exposure_outbox_notifications fails explicitly on digest mismatch."""
        state = MachineState()
        core0, env0 = _make_lexical_pair("القط", root_id=1, event_order=0)

        # Fake execution result with differing digest
        dummy_res = EventExecutionResult(
            event_order=0,
            exposure_id=1,
            mode=core0.origin,  # unused dummy
            origin=EventOrigin.EXTERNAL_DIRECT,
            boundary=True,
            committed_before_event=frozenset(),
            newly_committed_sensory_cells=(),
            obs_direct_cells=frozenset(),
            obs_eligible_cells=frozenset(),
            ctx_event_match_cells=frozenset(),
            ctx_runtime_match_cells=frozenset(),
            pt_by_cell={},
            ps_by_cell={},
            sigma_by_cell={},
            d1_by_cell={},
            a1_by_cell={},
            d2_by_cell={},
            a_plus_by_cell={},
            e1_frontier=frozenset(),
            l_frontier=frozenset(),
            lx_frontier=frozenset(),
            f_step=frozenset(),
            g_ctx_by_z={},
            g_probe_by_z={},
            mu_source_mask={},
            fresh_by_cell={},
            m_fresh_by_assembly={},
            typed_supports={},
            contributions=(),
            diagnostics=(),
            feature_bundle_digest=b"\x01" * 32,  # differing digest
        )

        asm = Assembly(
            assembly_id=1,
            region=Region.LANGUAGE,
            member_cell_ids=frozenset({8200, 8201, 8202}),
            structural_generation=1,
            status=AssemblyStatus.LIVE,
        )
        state.W.assemblies[1] = asm

        with pytest.raises(ObservationError) as exc_info:
            build_end_exposure_outbox_notifications(
                1,
                state.W,
                state.H_slow,
                [dummy_res],
                {0: env0},
                preexisting_live_assemblies=[asm],
            )
        assert exc_info.value.code == StatusCode.PROVENANCE_DIGEST_MISMATCH
