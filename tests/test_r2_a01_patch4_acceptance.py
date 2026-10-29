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
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from tests.test_r2_a01_patch2_acceptance import hash_state_snapshot


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

    # TEST C: State and Ledger Immutability
    from tests.test_r2_a01_patch2_acceptance import snapshot_w

    hash_w_pre = hash_state_snapshot(snapshot_w(state.W))
    ledger_rows_pre = {k: len(v) for k, v in attested_ledger._rows_by_asm_gen.items()}

    # Run generation with normal attested ledger
    gen_res_c = generate_episode(state, [prompt_ev], attested_ledger, max_steps=1)
    assert gen_res_c.emitted_surfaces == ("جميل",)

    hash_w_post = hash_state_snapshot(snapshot_w(state.W))
    ledger_rows_post = {k: len(v) for k, v in attested_ledger._rows_by_asm_gen.items()}

    # Exact byte-for-byte immutability
    assert hash_w_pre == hash_w_post, "W mutated during read-only generation episode"
    assert ledger_rows_pre == ledger_rows_post, "Ledger mutated during read-only generation"
