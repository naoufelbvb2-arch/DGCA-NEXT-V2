"""Acceptance test suite for R2-A01 Patch 4: Atomic State Publication and Outbox Recovery.

Normative references:
- DGCA_CORE_RC4_1.md §9.3, §9.4 (Peripheral Outbox, Readout Ledger, and Generation Stop Codes)
- DGCA_CORE_RC4_1.md §10.1, §10.2 (Exposure Lifecycle, Canonical Close Order, and Atomic Publication)
- DGCA_LLA_RC4_1.md §7 (Transaction Rules 1-4)
- R2-A01-REMEDIATION-DESIGN-CONTRACT.md Section 3.5 & Section 4 (Failure Injection Matrix)
- Acceptance scenarios: P5-01 through P5-06, FP-01 through FP-04.
"""

from __future__ import annotations

import copy
import pytest

from dgca.common.errors import ObservationError, StatusCode
from dgca.core.anatomy import SynapseScope
from dgca.core.generator import generate_episode
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import Assembly, AssemblyStatus, MachineState, Region
from dgca.encoder.envelope import Marker, encode_exposure, encode_lexical_token_event
from dgca.experiments.gates import _extract_f0_cells, _wire_consolidated_synapse
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
    TransactionPublicationView,
    frozendict,
)
from dgca.peripheral.outbox import OutboxNotificationV1
from dgca.peripheral.readout_ledger import LedgerCandidateRow, SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot, snapshot_ledger


def _setup_assemblies_for_events(
    state: MachineState,
    words: list[str],
    exposure_id: int = 1,
) -> None:
    """Pre-create LIVE Assemblies for a sequence of lexical tokens."""
    for idx, word in enumerate(words):
        ev = encode_lexical_token_event(
            word,
            exposure_id=exposure_id,
            event_order=idx,
            boundary=(idx == 0),
        )
        f0 = _extract_f0_cells(project_core_event_v1(ev.core_event))[:3]
        asm_id = idx + 1
        asm = Assembly(
            assembly_id=asm_id,
            region=Region.LANGUAGE,
            member_cell_ids=frozenset(f0),
            structural_generation=1,
            status=AssemblyStatus.LIVE,
        )
        state.W.assemblies[asm_id] = asm
        for c in f0:
            state.W.commit_cell(c, 0)
        for u in f0:
            for v in f0:
                if u != v:
                    _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL)


class FaultInjectableLedger(SurfaceReadoutLedgerV1):
    """Ledger that can deterministically raise errors during consume_outbox_batch."""

    def __init__(self, *, raise_on_batch: bool = False) -> None:
        super().__init__()
        self.raise_on_batch = raise_on_batch

    def consume_outbox_batch(self, batch: tuple[object, ...]) -> int:
        if self.raise_on_batch:
            raise RuntimeError("Transient ledger failure during consume_outbox_batch")
        return super().consume_outbox_batch(batch)


def test_p5_01_atomic_root_commit_success() -> None:
    """Scenario P5-01: Indivisible Atomic Root Commit Success.

    Valid OPEN root with peripheral envelopes commits atomically:
    - TransactionPublicationView pointer swap atomically publishes W and report.
    - Outbox delivered to peripheral ledger; pending queue cleared.
    - publication_view and completed_roots are immutable frozendicts.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    assert tx.publication_view.active_exposure_id == root_id

    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # Execute END_EXPOSURE
    rep = tx.end_exposure(root_id)

    # 1. State publication invariants
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.status == ExposureStatus.CLOSED
    assert tx.open_journal is None
    assert tx.publication_view.active_exposure_id is None
    assert tx.publication_view.completed_roots_high_watermark == root_id
    assert state.W.completed_roots_high_watermark == root_id
    assert state.W.close_serial == 1

    # 2. Immutability of publication view
    assert isinstance(tx.completed_roots, frozendict)
    assert root_id in tx.completed_roots
    assert tx.completed_roots[root_id] is rep
    with pytest.raises(TypeError, match="frozendict is immutable"):
        tx.completed_roots[999] = rep  # type: ignore[index]
    with pytest.raises(TypeError, match="frozendict is immutable"):
        tx.pending_outbox_by_root[999] = ()  # type: ignore[index]

    # 3. Post-commit dispatch succeeded; pending queue cleared
    assert tx.has_pending_outbox() is False
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count() == 0
    tx.assert_outbox_ready(root_id)  # Does not raise

    # 4. Ledger received outbox notifications
    assert len(ledger._rows_by_asm_gen) == 3
    for asm_id in (1, 2, 3):
        rows = ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].external_count == 1
        assert root_id in rows[0].confirmed_roots


def test_p5_02_pre_commit_failure_isolation() -> None:
    """Scenario P5-02: Pre-Commit Failure State Isolation & Sensory Retention (FP-01 & FP-02).

    Pre-commit failure during w_shadow preparation:
    - W not committed (close_serial == 0).
    - Root remains OPEN (retryable or abortable).
    - Zero attestations delivered to ledger.
    - Sensory cells admitted in process_event remain in state.W.
    """
    # SUBCASE A: FP-01 (failure during w_shadow candidate/assembly preparation)
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    committed_cells_pre_end = set(state.W.committed_cells.keys())
    assert len(committed_cells_pre_end) > 0

    # Inject FP-01 fault
    tx._fault_injection_point = "FP_01"
    with pytest.raises(RuntimeError, match="FP-01"):
        tx.end_exposure(root_id)

    # Invariants under FP-01:
    assert tx.status == ExposureStatus.OPEN
    assert tx.open_journal is not None
    assert root_id not in tx.completed_roots
    assert state.W.close_serial == 0
    assert len(ledger._rows_by_asm_gen) == 0  # Zero leakages to ledger
    # Core §10.1: Sensory commitments made during process_event remain
    assert set(state.W.committed_cells.keys()) == committed_cells_pre_end

    # Eligible to retry: clear fault and call end_exposure again
    tx._fault_injection_point = None
    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.status == ExposureStatus.CLOSED
    assert state.W.close_serial == 1

    # SUBCASE B: FP-02 (failure during outbox batch construction)
    root_id_2 = 2
    tx.begin_exposure(root_id_2)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id_2,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx._fault_injection_point = "FP_02"
    with pytest.raises(RuntimeError, match="FP-02"):
        tx.end_exposure(root_id_2)

    # Root remains OPEN; eligible to abort
    assert tx.status == ExposureStatus.OPEN
    status = tx.abort_exposure(root_id_2)
    assert status == ExposureStatus.ABORTED
    assert tx.status == ExposureStatus.CLOSED
    assert root_id_2 in tx.aborted_roots
    # Ledger has zero entries for root 2 (only root 1 entries from prior commit)
    for asm_id in (1, 2, 3):
        rows = ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert root_id_2 not in rows[0].confirmed_roots


def test_p5_03_post_commit_dispatch_failure() -> None:
    """Scenario P5-03: Post-Commit Outbox Delivery Failure Resilience (FP-03).

    When consume_outbox_batch fails after publication:
    - W remains committed (close_serial == 1).
    - Root status is COMPLETED.
    - Batch is safely preserved in pending_outbox_by_root.
    - Root is NOT retryable as OPEN.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # Injected fault at FP-03
    tx._fault_injection_point = "FP_03"
    rep = tx.end_exposure(root_id)

    # Invariants under FP-03:
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.status == ExposureStatus.CLOSED
    assert root_id in tx.completed_roots
    assert state.W.close_serial == 1
    assert state.W.completed_roots_high_watermark == root_id

    # Pending outbox batch is safely preserved
    assert tx.has_pending_outbox(root_id) is True
    assert tx.has_pending_outbox() is True
    assert tx.pending_outbox_count(root_id) == 3
    assert root_id in tx.pending_outbox_by_root

    # Root is COMPLETED, not abortable
    with pytest.raises(ObservationError, match="Cannot ABORT already COMPLETED root"):
        tx.abort_exposure(root_id)

    # Root cannot begin again (watermark strictly increasing)
    with pytest.raises(ObservationError, match="strictly increasing"):
        tx.begin_exposure(root_id)


def test_p5_04_orchestration_readiness() -> None:
    """Scenario P5-04: Explicit Orchestration Readiness Assertion.

    Un-delivered pending outbox batches block caller orchestration via
    ObservationError(StatusCode.OUTBOX_DELIVERY_PENDING).
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx._fault_injection_point = "FP_03"
    tx.end_exposure(root_id)

    # assert_outbox_ready with root_id
    with pytest.raises(ObservationError) as exc_info_root:
        tx.assert_outbox_ready(root_id)
    assert exc_info_root.value.code == StatusCode.OUTBOX_DELIVERY_PENDING
    assert str(root_id) in exc_info_root.value.message

    # assert_outbox_ready without root_id (across all pending roots)
    with pytest.raises(ObservationError) as exc_info_all:
        tx.assert_outbox_ready()
    assert exc_info_all.value.code == StatusCode.OUTBOX_DELIVERY_PENDING
    assert str(root_id) in exc_info_all.value.message


def test_p5_05_explicit_reconciliation() -> None:
    """Scenario P5-05: Explicit Outbox Reconciliation Recovery (FP-04).

    reconcile_outbox() redrives pending batches outside generation:
    - Transient ledger errors (FP-04) preserve pending batch for idempotent redrive.
    - Successful dispatch empties pending queue and enables assert_outbox_ready.
    - Idempotent: duplicate calls do not double attestations.
    """
    state = MachineState()
    faulty_ledger = FaultInjectableLedger(raise_on_batch=True)
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=faulty_ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # End exposure with faulty ledger: dispatch deferred
    tx.end_exposure(root_id)
    assert tx.has_pending_outbox(root_id) is True

    # FP-04: Transient failure during reconcile_outbox()
    with pytest.raises(RuntimeError, match="Transient ledger failure"):
        tx.reconcile_outbox(root_id, faulty_ledger)

    # Batch is retained after transient reconcile error
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    # Resolve fault and reconcile successfully
    faulty_ledger.raise_on_batch = False
    delivered = tx.reconcile_outbox(root_id, faulty_ledger)
    assert delivered == 3

    # Pending queue is now cleared
    assert tx.has_pending_outbox(root_id) is False
    assert tx.has_pending_outbox() is False
    assert tx.pending_outbox_count() == 0
    tx.assert_outbox_ready(root_id)  # Returns without raising

    # Duplicate call to reconcile_outbox is safe no-op
    delivered_again = tx.reconcile_outbox(root_id, faulty_ledger)
    assert delivered_again == 0

    # Ledger candidates are attested
    for asm_id in (1, 2, 3):
        rows = faulty_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert root_id in rows[0].confirmed_roots


def test_p5_06_generator_readout_safe_stops() -> None:
    """Scenario P5-06: Generator Readout Safe Stop Taxonomy & Immutability.

    Verifies normative stop codes during read-only rollout:
    - Test A: Missing/unattested row -> GEN_STOP_READOUT_UNKNOWN (never READOUT_UNAVAILABLE).
    - Test B: Ledger disabled (available=False) -> GEN_STOP_READOUT_UNAVAILABLE.
    - Test C: Read-only generation performs zero mutations on W and ledger.
    """
    from dgca.peripheral.outbox import OutboxNotificationV1
    from tests.test_phase6_readout_and_generation import (
        _connect_consolidated_synapse,
        _create_legal_triangle_assembly,
        _get_f0_and_all_cells,
        _make_envelope_pair,
    )

    state = MachineState()
    prompt_ev, _ = _make_envelope_pair("الطقس")
    proj_p = project_core_event_v1(prompt_ev)
    f0_p, all_p = _get_f0_and_all_cells(proj_p)
    for cid in all_p:
        state.W.commit_cell(cid, 0)

    # Winner Assembly #1 (s=0.90) vs Runner-up Assembly #2 (s=0.55)
    asm_winner = _create_legal_triangle_assembly(state, 1, (8300, 8308, 8316))
    asm_runner_up = _create_legal_triangle_assembly(state, 2, (8400, 8408, 8416))

    for src in f0_p[:3]:
        for tgt in asm_winner.member_cell_ids:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.90, scope=SynapseScope.ASSOCIATIVE
            )
        for tgt in asm_runner_up.member_cell_ids:
            _connect_consolidated_synapse(
                state, src, tgt, s_weight=0.55, scope=SynapseScope.ASSOCIATIVE
            )

    _, env_winner = _make_envelope_pair("جميل", root_id=1)

    # TEST A: Missing / Unattested row in ledger
    # Empty ledger: winner assembly 1 has no rows
    empty_ledger = SurfaceReadoutLedgerV1()
    gen_res_a = generate_episode(state, [prompt_ev], empty_ledger, max_steps=5)
    assert gen_res_a.stop_status == StatusCode.GEN_STOP_READOUT_UNKNOWN
    assert gen_res_a.stop_status != StatusCode.GEN_STOP_READOUT_UNAVAILABLE
    assert gen_res_a.stop_status != StatusCode.GEN_STOP_STALE_ASSEMBLY

    # TEST B: Ledger administratively unavailable (available=False)
    # Fully attest winner assembly 1 across 2 distinct roots
    attested_ledger = SurfaceReadoutLedgerV1()
    for rid in (1, 2):
        attested_ledger.consume_outbox_notification(
            OutboxNotificationV1(
                root_id=rid,
                event_order=0,
                assembly_id=asm_winner.assembly_id,
                structural_generation=asm_winner.structural_generation,
                surface_sha256=env_winner.surface_sha256,
                feature_bundle_digest=env_winner.feature_bundle_digest,
                marker=env_winner.marker,
                envelope=env_winner,
            )
        )
    assert (
        attested_ledger.resolve_readout(
            asm_winner.assembly_id, asm_winner.structural_generation
        ).status
        == StatusCode.OK
    )

    disabled_ledger = attested_ledger.clone()
    disabled_ledger.available = False
    gen_res_b = generate_episode(state, [prompt_ev], disabled_ledger, max_steps=5)
    assert gen_res_b.stop_status == StatusCode.GEN_STOP_READOUT_UNAVAILABLE
    assert gen_res_b.stop_status != StatusCode.GEN_STOP_READOUT_UNKNOWN

    # TEST C: Complete State and Ledger Immutability (Correction S04)
    from tests.test_r2_a01_patch2_acceptance import snapshot_ledger, snapshot_w

    snap_w_pre = snapshot_w(state.W)
    hash_w_pre = hash_state_snapshot(snap_w_pre)

    snap_l_pre = snapshot_ledger(attested_ledger)
    hash_l_pre = hash_state_snapshot(snap_l_pre)

    # Run generation with normal attested ledger
    gen_res_c = generate_episode(state, [prompt_ev], attested_ledger, max_steps=1)
    assert gen_res_c.emitted_surfaces == ("جميل",)

    snap_w_post = snapshot_w(state.W)
    hash_w_post = hash_state_snapshot(snap_w_post)

    snap_l_post = snapshot_ledger(attested_ledger)
    hash_l_post = hash_state_snapshot(snap_l_post)

    # Exact byte-for-byte structural and cryptographic immutability
    assert snap_w_pre == snap_w_post, "W structural snapshot mutated during read-only generation"
    assert hash_w_pre == hash_w_post, "W SHA-256 digest drifted during read-only generation"
    assert snap_l_pre == snap_l_post, "Ledger structural snapshot mutated during read-only generation"
    assert hash_l_pre == hash_l_post, "Ledger SHA-256 digest drifted during read-only generation"


def test_s01_no_silent_outbox_loss_on_unsupported_reconcile_consumer() -> None:
    """Correction S01: reconcile_outbox() with an unsupported consumer preserves pending batch.

    Mandatory regression:
    - Real completed root with 3 pending notifications.
    - tx.reconcile_outbox(exposure_id=root_id, ledger=object()).
    - Verify: no notification delivered, pending batch remains intact.
    - Readiness still reports OUTBOX_DELIVERY_PENDING.
    - Subsequent call with valid ledger successfully reconciles the complete batch.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=None,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx.end_exposure(root_id)

    # 1. Verify batch is pending
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    # 2. Call reconcile_outbox with unsupported consumer (lacking callable consume_outbox_batch)
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=object())
    assert delivered == 0

    # 3. Batch must remain 100% intact
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING

    # 4. Subsequent reconciliation with a valid ledger succeeds
    valid_ledger = SurfaceReadoutLedgerV1()
    reconciled = tx.reconcile_outbox(exposure_id=root_id, ledger=valid_ledger)
    assert reconciled == 3
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0
    tx.assert_outbox_ready(root_id)  # Does not raise
    assert len(valid_ledger._rows_by_asm_gen) == 3


def test_s01_no_silent_outbox_loss_on_unsupported_initial_dispatch() -> None:
    """Correction S01: end_exposure() with an unsupported ledger preserves pending batch.

    Mandatory regression:
    - Real open root with 3 events.
    - Initial dispatch supplied with unsupported ledger (object()).
    - W committed, root COMPLETED, but pending batch is preserved in publication view.
    - Readiness reports OUTBOX_DELIVERY_PENDING.
    - Subsequent reconcile_outbox() with valid ledger delivers complete batch.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=object(),  # Unsupported consumer type
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    rep = tx.end_exposure(root_id)

    # 1. Neural state committed; root COMPLETED (never rolled back)
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.status == ExposureStatus.CLOSED
    assert state.W.close_serial == 1
    assert root_id in tx.completed_roots

    # 2. Batch must be preserved in pending queue (not silently dropped)
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING

    # 3. Subsequent reconcile with valid ledger completes delivery
    valid_ledger = SurfaceReadoutLedgerV1()
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=valid_ledger)
    assert delivered == 3
    assert tx.has_pending_outbox(root_id) is False
    tx.assert_outbox_ready(root_id)


def test_s02_immutable_publication_metadata_adversarial() -> None:
    """Correction S02: Comprehensive adversarial mutation tests on frozendict publication metadata.

    Verifies that publication metadata cannot be modified via:
    - Direct item assignment (__setitem__)
    - In-place union (|= / __ior__)
    - update()
    - pop()
    - clear()
    - setdefault()
    - popitem()
    - Re-calling __init__()
    - References retained before subsequent publication swaps.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    rep1 = tx.end_exposure(root_id)

    published = tx.completed_roots
    pending = tx.pending_outbox_by_root
    forged_report = copy.copy(rep1)

    # 1. Direct item assignment
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published[999] = forged_report  # type: ignore[index]

    # 2. In-place union |= (__ior__)
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published |= {999: forged_report}  # type: ignore[misc]

    # 3. update()
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.update({999: forged_report})

    # 4. pop()
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.pop(root_id)

    # 5. clear()
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.clear()

    # 6. setdefault()
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.setdefault(999, forged_report)

    # 7. popitem()
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.popitem()

    # 8. Re-calling __init__()
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.__init__({999: forged_report})

    # 9. Base-class dict mutation bypasses (C02-S01)
    with pytest.raises(TypeError):
        dict.update(published, {999: forged_report})
    with pytest.raises(TypeError):
        dict.__setitem__(published, 998, forged_report)
    with pytest.raises(TypeError):
        dict.clear(published)

    # 10. Private attribute rebinding and deletion protection (C03-S04)
    from types import MappingProxyType
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published._proxy = MappingProxyType({})  # type: ignore[misc]
    with pytest.raises(TypeError, match="frozendict is immutable"):
        del published._proxy  # type: ignore[misc]

    # 11. Mutation of constructor source dict isolation
    source_dict = {100: forged_report}
    test_fd = frozendict(source_dict)
    source_dict[100] = None  # type: ignore[assignment]
    source_dict[101] = forged_report
    assert test_fd[100] is forged_report
    assert 101 not in test_fd

    # Same adversarial tests on pending mapping
    with pytest.raises(TypeError, match="frozendict is immutable"):
        pending[999] = ()  # type: ignore[index]
    with pytest.raises(TypeError, match="frozendict is immutable"):
        pending |= {999: ()}  # type: ignore[misc]

    # 12. Reference isolation across subsequent publication swaps
    retained_v1 = tx.completed_roots
    assert len(retained_v1) == 1
    assert root_id in retained_v1

    # Commit Root 2
    root_id_2 = 2
    tx.begin_exposure(root_id_2)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id_2,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)
    rep2 = tx.end_exposure(root_id_2)

    # Authoritative view now has 2 roots
    assert len(tx.completed_roots) == 2
    assert root_id_2 in tx.completed_roots

    # Retained v1 reference is 100% unchanged
    assert len(retained_v1) == 1
    assert root_id_2 not in retained_v1
    assert retained_v1[root_id] is rep1


def test_s03_precise_atomic_publication_visibility() -> None:
    """Correction S03: Authoritative publication boundary and visibility consistency.

    Verifies:
    - Before publication, completed root is absent from authoritative published view.
    - Pre-publication failure preserves OPEN journal status and tx.status == OPEN.
    - Single atomic swap updates (W, completed_roots, pending_outbox_by_root, watermark, active_id=None).
    - Readers capturing publication_view snapshot cannot observe mixed committed versions.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)

    # 1. Pre-publication checks
    assert tx.status == ExposureStatus.OPEN
    assert tx.publication_view.active_exposure_id == root_id
    assert root_id not in tx.publication_view.completed_roots
    assert tx.open_journal is not None
    assert tx.open_journal.status == ExposureStatus.OPEN

    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # 2. Before publication, journal status is still OPEN
    assert tx.open_journal.status == ExposureStatus.OPEN

    # 3. Controlled throwing hook during shadow preparation preserves OPEN journal status
    def throwing_hook(w_pre, w_shadow, h_slow, journal, diags):
        assert journal.status == ExposureStatus.OPEN, "Journal must be OPEN during preparation"
        raise RuntimeError("Controlled failure in shadow preparation hook")

    tx.register_end_exposure_hook(throwing_hook)

    with pytest.raises(RuntimeError, match="Controlled failure in shadow preparation hook"):
        tx.end_exposure(root_id)

    # Pre-publication failure guarantees:
    assert tx.status == ExposureStatus.OPEN
    assert tx.open_journal is not None
    assert tx.open_journal.status == ExposureStatus.OPEN
    assert root_id not in tx.publication_view.completed_roots
    assert tx.publication_view.active_exposure_id == root_id
    assert state.W.close_serial == 0
    assert len(ledger._rows_by_asm_gen) == 0

    # 4. Clear throwing hook and complete publication
    tx._end_exposure_hooks.clear()
    rep = tx.end_exposure(root_id)

    # Post-publication guarantees:
    pub = tx.publication_view
    assert pub.active_exposure_id is None
    assert root_id in pub.completed_roots
    assert pub.completed_roots[root_id] is rep
    assert pub.completed_roots_high_watermark == root_id
    assert pub.W.close_serial == 1
    assert tx.open_journal is None
    assert tx.status == ExposureStatus.CLOSED


def test_controlled_throwing_shadow_preparation_hook_fp01() -> None:
    """Section 6: Controlled throwing shadow preparation hook demonstrates FP-01 isolation.

    Verifies that real operational failure during shadow preparation:
    - Delivers 0 pre-commit peripheral attestations.
    - Leaves W uncommitted.
    - Leaves completed_roots empty.
    - Preserves admitted sensory commitments.
    - Leaves journal.status == OPEN.
    - Leaves root cleanly retryable or abortable.
    """
    state = MachineState()
    ledger = SurfaceReadoutLedgerV1()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    sensory_cells_admitted = set(state.W.committed_cells.keys())
    assert len(sensory_cells_admitted) > 0

    # Register actual operational throwing hook
    def throwing_preparation_hook(w_pre, w_shadow, h_slow, journal, diags):
        raise RuntimeError("Operational preparation error during shadow transaction")

    tx.register_end_exposure_hook(throwing_preparation_hook)

    with pytest.raises(RuntimeError, match="Operational preparation error"):
        tx.end_exposure(root_id)

    # Invariants:
    assert tx.status == ExposureStatus.OPEN
    assert tx.open_journal is not None
    assert tx.open_journal.status == ExposureStatus.OPEN
    assert root_id not in tx.completed_roots
    assert state.W.close_serial == 0
    assert len(ledger._rows_by_asm_gen) == 0  # 0 peripheral attestations
    assert set(state.W.committed_cells.keys()) == sensory_cells_admitted  # Sensory retention

    # Clean abort capability
    abort_status = tx.abort_exposure(root_id)
    assert abort_status == ExposureStatus.ABORTED
    assert tx.status == ExposureStatus.CLOSED
    assert root_id in tx.aborted_roots
    assert set(state.W.committed_cells.keys()) == sensory_cells_admitted


class NoOpLedger:
    """Callable outbox consumer that returns 0 without consuming or acknowledging (C02-S02)."""

    def consume_outbox_batch(self, batch: object) -> int:
        return 0


class PartialFailingLedger(SurfaceReadoutLedgerV1):
    """Consumer that consumes up to `fail_after` notifications before raising an exception (C02-S02)."""

    def __init__(self, fail_after: int = 1) -> None:
        super().__init__()
        self.fail_after = fail_after

    def consume_outbox_batch(self, batch: Sequence[OutboxNotificationV1]) -> int:
        added = 0
        for i, notif in enumerate(batch):
            if i >= self.fail_after:
                raise RuntimeError("Simulated transient transport failure during batch")
            if self.consume_outbox_notification(notif):
                added += 1
        return added


def test_c02_s02_a_valid_consumer_first_delivery() -> None:
    """C02-S02 Test A: Valid consumer, first delivery.

    All notifications acknowledged. Pending batch cleared.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=None,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx.end_exposure(root_id)
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    valid_ledger = SurfaceReadoutLedgerV1()
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=valid_ledger)
    assert delivered == 3
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0
    tx.assert_outbox_ready(root_id)

    # All candidate rows confirmed
    for asm_id in (1, 2, 3):
        rows = valid_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert root_id in rows[0].confirmed_roots


def test_c02_s02_b_valid_consumer_duplicate_delivery() -> None:
    """C02-S02 Test B: Valid consumer, duplicate delivery.

    Already-processed idempotency keys count as acknowledged. No duplicate confirmations.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    valid_ledger = SurfaceReadoutLedgerV1()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=valid_ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx.end_exposure(root_id)
    # Delivered during initial post-commit
    assert tx.has_pending_outbox(root_id) is False

    # Simulate re-queuing duplicate batch in pending view (e.g. replay scenario)
    batch = tuple(
        OutboxNotificationV1(
            root_id=root_id,
            event_order=item.core_event.event_order,
            assembly_id=i + 1,
            structural_generation=1,
            surface_sha256=item.peripheral_surface.surface_sha256,
            feature_bundle_digest=item.peripheral_surface.feature_bundle_digest,
            marker=item.peripheral_surface.marker,
            envelope=item.peripheral_surface,
        )
        for i, item in enumerate(envs)
    )
    tx._publication_view = TransactionPublicationView(
        W=tx._publication_view.W,
        completed_roots=tx._publication_view.completed_roots,
        pending_outbox_by_root=frozendict({root_id: batch}),
        completed_roots_high_watermark=tx._publication_view.completed_roots_high_watermark,
        active_exposure_id=None,
    )
    assert tx.has_pending_outbox(root_id) is True

    # Duplicate delivery: method returns 0 new additions, but all notifications are acknowledged
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=valid_ledger)
    assert delivered == 0
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0

    # Confirm no duplicate root additions in candidate rows
    for asm_id in (1, 2, 3):
        rows = valid_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].confirmed_roots == {root_id}


def test_c02_s02_c_callable_noop_consumer() -> None:
    """C02-S02 Test C: Callable no-op consumer.

    Method returns without consuming. Pending batch preserved.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=None,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx.end_exposure(root_id)
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    # Reconcile with callable no-op consumer
    noop_ledger = NoOpLedger()
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=noop_ledger)
    assert delivered == 0
    # Pending batch must be preserved!
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING


def test_c02_s02_d_unsupported_consumer() -> None:
    """C02-S02 Test D: Unsupported consumer.

    Consumer lacks consume_outbox_batch. Pending batch preserved.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=None,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx.end_exposure(root_id)
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    # Reconcile with object()
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=object())
    assert delivered == 0
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3


def test_c02_s02_e_partial_delivery_and_exception() -> None:
    """C02-S02 Test E: Partial delivery and exception.

    Pending batch preserved. Later reconciliation succeeds without duplication.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=None,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    tx.end_exposure(root_id)
    assert tx.has_pending_outbox(root_id) is True

    # 1. Partial delivery throws after consuming 1 notification
    failing_ledger = PartialFailingLedger(fail_after=1)
    with pytest.raises(RuntimeError, match="Simulated transient transport failure"):
        tx.reconcile_outbox(exposure_id=root_id, ledger=failing_ledger)

    # Batch is retained
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3
    assert len(failing_ledger._processed_outbox_keys) == 1

    # 2. Re-drive reconciliation with fault cleared
    failing_ledger.fail_after = 99
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=failing_ledger)
    assert delivered == 2  # Only the remaining 2 notifications newly added
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0
    assert len(failing_ledger._processed_outbox_keys) == 3

    # Invariants: no duplicate root observations
    for asm_id in (1, 2, 3):
        rows = failing_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].confirmed_roots == {root_id}


def test_c02_s02_f_initial_post_commit_noop_delivery() -> None:
    """C02-S02 Test F: Initial post-commit no-op delivery.

    Neural W remains committed. Root remains COMPLETED. Pending batch remains recoverable.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    noop_ledger = NoOpLedger()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=noop_ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    rep = tx.end_exposure(root_id)

    # 1. Core neural state W is committed
    assert rep.status == ExposureStatus.COMPLETED
    assert state.W.close_serial == 1
    assert tx.status == ExposureStatus.CLOSED
    assert root_id in tx.completed_roots

    # 2. Pending batch preserved despite no-op ledger returning successfully
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING

    # 3. Recoverable via explicit reconciliation with valid ledger
    valid_ledger = SurfaceReadoutLedgerV1()
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=valid_ledger)
    assert delivered == 3
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0
    tx.assert_outbox_ready(root_id)


class MidNotificationFaultLedger(SurfaceReadoutLedgerV1):
    """Ledger designed to deterministically simulate mid-notification failures (C03-S02)."""

    def __init__(
        self,
        *,
        fail_before_candidate_row: bool = False,
        fail_after_candidate_row: bool = False,
        fail_at_notif_index: int | None = None,
    ) -> None:
        super().__init__()
        self.fail_before_candidate_row = fail_before_candidate_row
        self.fail_after_candidate_row = fail_after_candidate_row
        self.fail_at_notif_index = fail_at_notif_index
        self._notif_call_count = 0

    def consume_outbox_notification(self, notif: OutboxNotificationV1) -> bool:
        idx = self._notif_call_count
        self._notif_call_count += 1

        should_fail_this_notif = (
            self.fail_at_notif_index is None or self.fail_at_notif_index == idx
        )

        if should_fail_this_notif and self.fail_before_candidate_row:
            # Simulate failure after idempotency key would historically have been added,
            # but before candidate evidence is fully recorded
            raise RuntimeError("Injected failure before candidate evidence recording")

        if should_fail_this_notif and self.fail_after_candidate_row:
            # Perform candidate row update, then raise before acknowledgment finalization
            asm_key = (notif.assembly_id, notif.structural_generation)
            row_map = self._rows_by_asm_gen.setdefault(asm_key, {})
            t_key = (
                notif.envelope.surface_utf8_nfc,
                notif.marker,
                notif.feature_bundle_digest,
            )
            surf_key = (
                notif.assembly_id,
                notif.structural_generation,
                notif.envelope.surface_utf8_nfc,
                notif.marker,
            )
            self._bundles_by_surface.setdefault(surf_key, set()).add(notif.feature_bundle_digest)
            row = row_map.get(t_key)
            if row is None:
                row = LedgerCandidateRow(
                    assembly_id=notif.assembly_id,
                    structural_generation=notif.structural_generation,
                    surface_utf8_nfc=notif.envelope.surface_utf8_nfc,
                    marker=notif.marker,
                    surface_sha256=notif.surface_sha256,
                    feature_bundle_digest=notif.feature_bundle_digest,
                    envelope=notif.envelope,
                    confirmed_roots={notif.root_id},
                )
                row_map[t_key] = row
            else:
                row.confirmed_roots.add(notif.root_id)
            # Raise exception before _processed_outbox_keys.add(idem_key)
            raise RuntimeError(
                "Injected failure after candidate row update but before acknowledgment finalization"
            )

        return super().consume_outbox_notification(notif)


def test_c03_s02_mid_notification_failure_before_evidence() -> None:
    """C03-S02: Mid-notification failure before candidate evidence is recorded.

    Mandatory assertions:
    - Failure injected during post-commit delivery.
    - Neural W remains committed; root remains COMPLETED.
    - Batch remains pending in publication view.
    - No false successful acknowledgment is reported.
    - No incomplete notification permanently poisoned or marked consumed.
    - Explicit reconciliation succeeds after fault removed.
    - All keys acknowledged, all evidence recorded, no duplicate root confirmations.
    - Repeated replay is safe no-op.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    fault_ledger = MidNotificationFaultLedger(fail_before_candidate_row=True)
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=fault_ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # 1. End exposure triggers post-commit delivery which encounters injected failure
    rep = tx.end_exposure(root_id)

    # Invariants after failure:
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.status == ExposureStatus.CLOSED
    assert state.W.close_serial == 1
    assert root_id in tx.completed_roots

    # Batch remains pending
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    # No false acknowledgment
    batch = tx.pending_outbox_by_root[root_id]
    assert fault_ledger.is_batch_acknowledged(batch) is False
    assert len(fault_ledger._processed_outbox_keys) == 0
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING

    # 2. Clear fault and redrive via reconcile_outbox
    fault_ledger.fail_before_candidate_row = False
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=fault_ledger)
    assert delivered == 3

    # Invariants after successful reconciliation:
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0
    tx.assert_outbox_ready(root_id)
    assert fault_ledger.is_batch_acknowledged(batch) is True
    assert len(fault_ledger._processed_outbox_keys) == 3

    # All candidate evidence exists with exact single root confirmation
    for asm_id in (1, 2, 3):
        rows = fault_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].confirmed_roots == {root_id}

    # 3. Repeated replay test
    delivered_replay = tx.reconcile_outbox(exposure_id=root_id, ledger=fault_ledger)
    assert delivered_replay == 0
    for asm_id in (1, 2, 3):
        rows = fault_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].confirmed_roots == {root_id}


def test_c03_s02_failure_after_candidate_row_before_ack() -> None:
    """C03-S02: Failure after candidate row update but before acknowledgment finalization.

    Mandatory assertions:
    - Candidate row was updated, but exception raised before key recorded.
    - Batch remains pending; is_batch_acknowledged returns False.
    - Subsequent reconciliation finalizes acknowledgment without duplicate confirmations.
    - Repeated replay produces 0 additions and leaves confirmed roots unchanged.
    """
    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    fault_ledger = MidNotificationFaultLedger(fail_after_candidate_row=True, fail_at_notif_index=0)
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=fault_ledger,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # 1. End exposure
    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.has_pending_outbox(root_id) is True

    # First candidate row was updated, but not acknowledged because key was not added
    batch = tx.pending_outbox_by_root[root_id]
    assert fault_ledger.is_batch_acknowledged(batch) is False
    assert fault_ledger.is_notification_acknowledged(batch[0]) is False

    # 2. Clear fault and reconcile
    fault_ledger.fail_after_candidate_row = False
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=fault_ledger)
    # The first row was already confirmed; the other 2 rows are newly confirmed
    assert delivered == 2
    assert tx.has_pending_outbox(root_id) is False
    assert fault_ledger.is_batch_acknowledged(batch) is True
    assert len(fault_ledger._processed_outbox_keys) == 3

    # Verify no duplicate root confirmation for any candidate row
    for asm_id in (1, 2, 3):
        rows = fault_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].confirmed_roots == {root_id}

    # 3. Replay
    delivered_again = tx.reconcile_outbox(exposure_id=root_id, ledger=fault_ledger)
    assert delivered_again == 0
    for asm_id in (1, 2, 3):
        rows = fault_ledger.get_candidate_rows(asm_id, 1)
        assert len(rows) == 1
        assert rows[0].confirmed_roots == {root_id}


def test_c03_s03_acknowledgment_evidence_correspondence() -> None:
    """C03-S03: Verify acknowledgment corresponds strictly to completed evidence.

    Tests that:
    - Premature key registration without candidate evidence is rejected.
    - Candidate row without confirmed root is rejected.
    - Surface bundle missing is rejected.
    - Third-party callback attempting to report True when evidence is missing is rejected.
    - Only complete correspondence satisfies acknowledgment.
    """
    from dgca.lifecycle.exposure_tx import _is_batch_acknowledged

    envs = encode_exposure("القط", append_eos=False)
    notif = OutboxNotificationV1(
        root_id=1,
        event_order=0,
        assembly_id=1,
        structural_generation=1,
        surface_sha256=envs[0].peripheral_surface.surface_sha256,
        feature_bundle_digest=envs[0].peripheral_surface.feature_bundle_digest,
        marker=envs[0].peripheral_surface.marker,
        envelope=envs[0].peripheral_surface,
    )

    ledger = SurfaceReadoutLedgerV1()

    # 1. Empty ledger
    assert ledger.is_notification_acknowledged(notif) is False
    assert ledger.is_batch_acknowledged([notif]) is False
    assert _is_batch_acknowledged(ledger, [notif]) is False

    # 2. Premature key registration without candidate row
    ledger._processed_outbox_keys.add(notif.idempotency_key)
    assert ledger.is_notification_acknowledged(notif) is False
    assert ledger.is_batch_acknowledged([notif]) is False
    assert _is_batch_acknowledged(ledger, [notif]) is False

    # 3. Candidate row added, but confirmed_roots does not contain notif.root_id
    asm_key = (notif.assembly_id, notif.structural_generation)
    t_key = (notif.envelope.surface_utf8_nfc, notif.marker, notif.feature_bundle_digest)
    surf_key = (
        notif.assembly_id,
        notif.structural_generation,
        notif.envelope.surface_utf8_nfc,
        notif.marker,
    )
    row = LedgerCandidateRow(
        assembly_id=notif.assembly_id,
        structural_generation=notif.structural_generation,
        surface_utf8_nfc=notif.envelope.surface_utf8_nfc,
        marker=notif.marker,
        surface_sha256=notif.surface_sha256,
        feature_bundle_digest=notif.feature_bundle_digest,
        envelope=notif.envelope,
        confirmed_roots={999},  # Different root!
    )
    ledger._rows_by_asm_gen[asm_key] = {t_key: row}
    ledger._bundles_by_surface[surf_key] = {notif.feature_bundle_digest}
    assert ledger.is_notification_acknowledged(notif) is False
    assert ledger.is_batch_acknowledged([notif]) is False
    assert _is_batch_acknowledged(ledger, [notif]) is False

    # 4. Now add notif.root_id to confirmed_roots: complete evidence satisfied
    row.confirmed_roots.add(notif.root_id)
    assert ledger.is_notification_acknowledged(notif) is True
    assert ledger.is_batch_acknowledged([notif]) is True
    assert _is_batch_acknowledged(ledger, [notif]) is True

    # 5. Third-party consumer attempting to report True when canonical evidence is missing
    class FlakyConsumer:
        def __init__(self) -> None:
            self._rows_by_asm_gen = {}
            self._processed_outbox_keys = {notif.idempotency_key}

        def is_batch_acknowledged(self, batch: object) -> bool:
            return True  # Flaky callback claiming success

    flaky = FlakyConsumer()
    # Guard blocks acceptance because _rows_by_asm_gen is missing candidate evidence
    assert _is_batch_acknowledged(flaky, [notif]) is False


def test_c03_s04_frozendict_slot_rebinding_protection() -> None:
    """C03-S04: Prevent ordinary attribute assignment or deletion from replacing frozendict internals.

    Verifies:
    - _proxy cannot be rebound on published completed_roots or pending_outbox_by_root.
    - _proxy cannot be deleted via del or delattr.
    - _hash cannot be rebound or deleted.
    - Arbitrary attributes cannot be set.
    - Constructor, mapping lookups, copy, deepcopy, and hash behavior remain intact.
    """
    from types import MappingProxyType

    state = MachineState()
    _setup_assemblies_for_events(state, ["القط"])
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
    )
    tx.begin_exposure(1)
    ev = encode_exposure("القط", append_eos=False)[0]
    core_ev = encode_lexical_token_event(
        ev.peripheral_surface.raw_surface_nfc_utf8,
        exposure_id=1,
        event_order=0,
        boundary=True,
    ).core_event
    tx.process_event(core_ev, peripheral_envelope=ev.peripheral_surface)
    tx.end_exposure(1)

    published = tx.completed_roots
    pending = tx.pending_outbox_by_root

    # 1. _proxy attribute assignment blocked
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published._proxy = MappingProxyType({})  # type: ignore[misc]

    with pytest.raises(TypeError, match="frozendict is immutable"):
        setattr(published, "_proxy", MappingProxyType({}))

    with pytest.raises(TypeError, match="frozendict is immutable"):
        pending._proxy = MappingProxyType({})  # type: ignore[misc]

    # 2. _proxy deletion blocked
    with pytest.raises(TypeError, match="frozendict is immutable"):
        del published._proxy  # type: ignore[misc]

    with pytest.raises(TypeError, match="frozendict is immutable"):
        delattr(published, "_proxy")

    with pytest.raises(TypeError, match="frozendict is immutable"):
        del pending._proxy  # type: ignore[misc]

    # 3. _hash attribute assignment and deletion blocked
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published._hash = 999  # type: ignore[misc]

    with pytest.raises(TypeError, match="frozendict is immutable"):
        del published._hash  # type: ignore[misc]

    # 4. Arbitrary attribute assignment blocked
    with pytest.raises(TypeError, match="frozendict is immutable"):
        published.arbitrary = 123  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match="frozendict is immutable"):
        setattr(published, "arbitrary", 123)

    # 5. Core functionality intact
    assert len(published) == 1
    assert 1 in published
    test_fd = frozendict({"a": 1, "b": 2})
    assert test_fd["a"] == 1
    assert hash(test_fd) is not None
    assert copy.copy(test_fd) == test_fd
    assert copy.deepcopy(test_fd) == test_fd


class KeyOnlyConsumer:
    """Consumer exposing only raw idempotency key sets without candidate evidence (C04-S01)."""

    def __init__(self) -> None:
        self._processed_outbox_keys: set[object] = set()

    def consume_outbox_batch(self, batch: Sequence[object]) -> int:
        for notification in batch:
            self._processed_outbox_keys.add(notification.idempotency_key)  # type: ignore[attr-defined]
        return len(batch)


def test_c04_s01_key_only_consumer_rejected() -> None:
    """Correction C04-S01: Key-only consumer without acknowledgment interface or evidence is rejected.

    Mandatory test:
    - Real completed root with 3 pending notifications.
    - Consumer invocation succeeds and records raw keys.
    - No candidate evidence exists in consumer.
    - Acknowledgment verification returns False.
    - Pending Outbox remains intact in publication view.
    - assert_outbox_ready() continues raising OUTBOX_DELIVERY_PENDING.
    - Subsequent reconciliation with the canonical ledger succeeds.
    """
    from dgca.lifecycle.exposure_tx import _is_batch_acknowledged

    state = MachineState()
    _setup_assemblies_for_events(state, ["القط", "يشرب", "حليب"])

    key_consumer = KeyOnlyConsumer()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=key_consumer,
    )

    envs = encode_exposure("القط يشرب حليب", append_eos=False)
    root_id = 1
    tx.begin_exposure(root_id)
    for item in envs:
        core_ev = encode_lexical_token_event(
            item.peripheral_surface.raw_surface_nfc_utf8,
            exposure_id=root_id,
            event_order=item.core_event.event_order,
            boundary=item.core_event.boundary,
        ).core_event
        tx.process_event(core_ev, peripheral_envelope=item.peripheral_surface)

    # 1. End exposure: initial post-commit dispatch runs key_consumer.consume_outbox_batch()
    rep = tx.end_exposure(root_id)

    # Invariants:
    assert rep.status == ExposureStatus.COMPLETED
    assert tx.status == ExposureStatus.CLOSED
    assert state.W.close_serial == 1
    assert root_id in tx.completed_roots

    # Consumer invocation succeeded and keys are recorded in its raw set
    assert len(key_consumer._processed_outbox_keys) == 3

    # Acknowledgment verification returns False
    batch = tx.pending_outbox_by_root[root_id]
    assert _is_batch_acknowledged(key_consumer, batch) is False

    # Pending outbox remains intact
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING

    # 2. Reconcile explicitly with key_consumer: invocation succeeds, but batch is still retained
    delivered = tx.reconcile_outbox(exposure_id=root_id, ledger=key_consumer)
    assert delivered == 0
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3

    # 3. Subsequent reconciliation with canonical ledger succeeds completely
    canonical_ledger = SurfaceReadoutLedgerV1()
    delivered_canon = tx.reconcile_outbox(exposure_id=root_id, ledger=canonical_ledger)
    assert delivered_canon == 3
    assert tx.has_pending_outbox(root_id) is False
    assert tx.pending_outbox_count(root_id) == 0
    tx.assert_outbox_ready(root_id)
    assert canonical_ledger.is_batch_acknowledged(batch) is True
    assert _is_batch_acknowledged(canonical_ledger, batch) is True


def test_c04_s02_real_production_rollback_fresh_ledger() -> None:
    """Correction C04-S02: Directly exercise real production rollback block on a fresh ledger.

    Approach:
    1. Construct real valid OutboxNotificationV1.
    2. Capture complete ledger snapshot and SHA-256 digest.
    3. Inject controlled failure into _processed_outbox_keys.add() after candidate and bundle evidence are updated.
    4. Invoke original production consume_outbox_notification() method.
    5. Verify exception propagates.
    6. Verify exact ledger snapshot and SHA-256 equality with pre-operation state.
    7. Remove fault and retry.
    8. Confirm exactly one lawful root observation and successful acknowledgment.
    """
    envs = encode_exposure("القط", append_eos=False)
    notif = OutboxNotificationV1(
        root_id=1,
        event_order=0,
        assembly_id=1,
        structural_generation=1,
        surface_sha256=envs[0].peripheral_surface.surface_sha256,
        feature_bundle_digest=envs[0].peripheral_surface.feature_bundle_digest,
        marker=envs[0].peripheral_surface.marker,
        envelope=envs[0].peripheral_surface,
    )

    ledger = SurfaceReadoutLedgerV1()
    snap_pre = snapshot_ledger(ledger)
    hash_pre = hash_state_snapshot(snap_pre)

    class FailingSet(set):
        def add(self, item: object) -> None:
            raise RuntimeError("Injected failure during _processed_outbox_keys.add()")

    # Inject failure into the final step of the production method
    ledger._processed_outbox_keys = FailingSet()

    # 4. Invoke original production method
    with pytest.raises(RuntimeError, match="Injected failure during _processed_outbox_keys.add()"):
        ledger.consume_outbox_notification(notif)

    # 6. Verify exact ledger snapshot and digest equality with pre-operation state
    snap_post = snapshot_ledger(ledger)
    hash_post = hash_state_snapshot(snap_post)

    assert snap_pre == snap_post, "Ledger structural snapshot drifted after rollback!"
    assert hash_pre == hash_post, "Ledger cryptographic SHA-256 digest drifted after rollback!"
    assert len(ledger._rows_by_asm_gen) == 0
    assert len(ledger._bundles_by_surface) == 0
    assert len(ledger._processed_outbox_keys) == 0

    # 7. Remove fault and retry
    ledger._processed_outbox_keys = set()
    added = ledger.consume_outbox_notification(notif)
    assert added is True

    # 8. Confirm exactly one lawful root observation and acknowledgment
    assert ledger.is_notification_acknowledged(notif) is True
    rows = ledger.get_candidate_rows(1, 1)
    assert len(rows) == 1
    assert rows[0].confirmed_roots == {1}


def test_c04_s02_real_production_rollback_existing_candidate_row() -> None:
    """Correction C04-S02: Directly exercise real production rollback with a pre-existing candidate row.

    Verifies:
    - Pre-existing root (root 99) in candidate row is completely preserved.
    - Failed new root confirmation (root 1) is rolled back cleanly.
    - Snapshot and SHA-256 digest match pre-operation state exactly.
    - Retry successfully confirms root 1 without duplicate observations or loss of root 99.
    """
    envs = encode_exposure("القط", append_eos=False)
    notif_prior = OutboxNotificationV1(
        root_id=99,
        event_order=0,
        assembly_id=1,
        structural_generation=1,
        surface_sha256=envs[0].peripheral_surface.surface_sha256,
        feature_bundle_digest=envs[0].peripheral_surface.feature_bundle_digest,
        marker=envs[0].peripheral_surface.marker,
        envelope=envs[0].peripheral_surface,
    )

    ledger = SurfaceReadoutLedgerV1()
    # Establish pre-existing candidate row with root 99
    added_prior = ledger.consume_outbox_notification(notif_prior)
    assert added_prior is True
    assert ledger.is_notification_acknowledged(notif_prior) is True

    snap_pre = snapshot_ledger(ledger)
    hash_pre = hash_state_snapshot(snap_pre)

    # Now prepare notification for root 1 for the same candidate tuple
    notif_new = OutboxNotificationV1(
        root_id=1,
        event_order=0,
        assembly_id=1,
        structural_generation=1,
        surface_sha256=envs[0].peripheral_surface.surface_sha256,
        feature_bundle_digest=envs[0].peripheral_surface.feature_bundle_digest,
        marker=envs[0].peripheral_surface.marker,
        envelope=envs[0].peripheral_surface,
    )

    class FailingSet(set):
        def add(self, item: object) -> None:
            raise RuntimeError("Injected failure during _processed_outbox_keys.add()")

    failing_keys = FailingSet(ledger._processed_outbox_keys)
    ledger._processed_outbox_keys = failing_keys

    # Invoke production method
    with pytest.raises(RuntimeError, match="Injected failure during _processed_outbox_keys.add()"):
        ledger.consume_outbox_notification(notif_new)

    # Verify exact rollback: pre-existing root 99 preserved, root 1 reverted
    snap_post = snapshot_ledger(ledger)
    hash_post = hash_state_snapshot(snap_post)

    assert snap_pre == snap_post, "Ledger snapshot drifted after existing-row rollback!"
    assert hash_pre == hash_post, "Ledger cryptographic SHA-256 digest drifted after existing-row rollback!"
    rows_post = ledger.get_candidate_rows(1, 1)
    assert len(rows_post) == 1
    assert rows_post[0].confirmed_roots == {99}
    assert 1 not in rows_post[0].confirmed_roots

    # Remove fault and retry
    ledger._processed_outbox_keys = set(failing_keys)
    added_new = ledger.consume_outbox_notification(notif_new)
    assert added_new is True

    # Both roots now confirmed lawfully; exactly one candidate row
    assert ledger.is_notification_acknowledged(notif_prior) is True
    assert ledger.is_notification_acknowledged(notif_new) is True
    rows_final = ledger.get_candidate_rows(1, 1)
    assert len(rows_final) == 1
    assert rows_final[0].confirmed_roots == {99, 1}
