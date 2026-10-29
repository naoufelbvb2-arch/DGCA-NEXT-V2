"""Forensic Investigation F01-02: OUTBOX_ATOMICITY_AND_FAILURE_INJECTION (R1-B02 & Task 7 Normalized).

Historical context (R1-B02):
- Pre-remediation DGCA v2 consumed peripheral outbox batches BEFORE atomic W publication.
- Failures during outbox delivery leaked partial attestations for uncommitted roots that could subsequently abort.

Remediated invariants (R2-A01 Patch 4):
1. Pre-commit failures (FP-01 / FP-02) never touch peripheral ledger (0 attempts, 0 confirmations).
2. Atomic publication occurs via single pointer swap (_publication_view) BEFORE peripheral dispatch.
3. Post-commit dispatch failures (FP-03) defer batch into pending_outbox_by_root without uncommitting W.
4. Completed roots cannot be aborted; orchestration barrier assert_outbox_ready() traps pending delivery.
5. Explicit reconciliation (reconcile_outbox) delivers pending batches idempotently.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import ObservationError, StatusCode
from dgca.core.anatomy import SynapseScope
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import Assembly, AssemblyStatus, MachineState, Region
from dgca.encoder.envelope import encode_exposure, encode_lexical_token_event
from dgca.experiments.gates import _extract_f0_cells, _wire_consolidated_synapse
from dgca.lifecycle.exposure_tx import ExposureStatus, ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


class ConfigurableFaultLedger(SurfaceReadoutLedgerV1):
    """Diagnostic ledger with controlled fault injection at precise points."""

    def __init__(self, fail_point: str) -> None:
        super().__init__()
        self.fail_point = fail_point
        self.delivery_attempts = 0
        self.accepted_confirmations = 0

    def consume_outbox_batch(self, batch: tuple[object, ...]) -> int:
        if self.fail_point == "BEFORE_PROCESSING":
            raise RuntimeError("FAULT: before notification processing")

        added = 0
        for idx, notif in enumerate(batch):
            self.delivery_attempts += 1
            if self.fail_point == "AFTER_FIRST" and idx == 1:
                raise RuntimeError("FAULT: after first notification")
            if self.fail_point == "DURING_LATER" and idx == 2:
                raise RuntimeError("FAULT: during later notification (idx=2)")

            res = super().consume_outbox_notification(notif)
            if res:
                self.accepted_confirmations += 1
                added += 1

        if self.fail_point == "BEFORE_W_PUBLICATION":
            raise RuntimeError("FAULT: dispatch failure")
        return added


def _setup_open_root_with_three_assemblies(ledger: SurfaceReadoutLedgerV1) -> tuple[MachineState, ExposureTransactionManager, int]:
    state = MachineState()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )

    # Encode 3 real events to get 3 matching Assemblies
    ev_a = encode_lexical_token_event("القط", exposure_id=1, event_order=0, boundary=True)
    ev_b = encode_lexical_token_event("يشرب", exposure_id=1, event_order=1, boundary=False)
    ev_c = encode_lexical_token_event("حليب", exposure_id=1, event_order=2, boundary=False)
    f0_cat = _extract_f0_cells(project_core_event_v1(ev_a.core_event))[:3]
    f0_drinks = _extract_f0_cells(project_core_event_v1(ev_b.core_event))[:3]
    f0_milk = _extract_f0_cells(project_core_event_v1(ev_c.core_event))[:3]

    for asm_id, f0 in [(1, f0_cat), (2, f0_drinks), (3, f0_milk)]:
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

    # Process events with envelopes
    root_id = 1
    tx.begin_exposure(root_id)
    tx.process_event(ev_a.core_event, peripheral_envelope=ev_a.peripheral_surface)
    tx.process_event(ev_b.core_event, peripheral_envelope=ev_b.peripheral_surface)
    tx.process_event(ev_c.core_event, peripheral_envelope=ev_c.peripheral_surface)
    return state, tx, root_id


def test_f01_02_scenario_1_pre_commit_failure_zero_attestations() -> None:
    """Scenario 1: Pre-commit fault (FP-01 / FP-02) leaves ledger untouched and root OPEN."""
    ledger = ConfigurableFaultLedger(fail_point="NONE")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    # Inject pre-commit fault
    tx._fault_injection_point = "FP_01"
    with pytest.raises(RuntimeError, match="FP-01"):
        tx.end_exposure(root_id)

    # Root remains OPEN; W uncommitted; exactly 0 ledger interactions
    assert tx.status == ExposureStatus.OPEN
    assert root_id not in tx.completed_roots
    assert state.W.close_serial == 0
    assert ledger.delivery_attempts == 0
    assert ledger.accepted_confirmations == 0
    assert len(ledger._rows_by_asm_gen) == 0

    # Sensory commitments from process_event remain preserved
    assert len(state.W.committed_cells) > 0

    # Root is still cleanly abortable
    tx.abort_exposure(root_id)
    assert tx.status == ExposureStatus.CLOSED
    assert ledger.delivery_attempts == 0
    assert ledger.accepted_confirmations == 0


def test_f01_02_scenario_2_post_commit_dispatch_partial_failure() -> None:
    """Scenario 2: Post-commit dispatch failure preserves committed W and defers pending batch."""
    ledger = ConfigurableFaultLedger(fail_point="AFTER_FIRST")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED

    # Root is COMPLETED and W is committed (no rollback)
    assert tx.status == ExposureStatus.CLOSED
    assert root_id in tx.completed_roots
    assert state.W.close_serial == 1

    # Attestation in ledger belongs to a COMMITTED root, eliminating R1-B02 leakage
    assert ledger.accepted_confirmations == 1

    # Pending batch is retained for explicit reconciliation
    assert tx.has_pending_outbox(root_id) is True
    assert tx.pending_outbox_count(root_id) == 3


def test_f01_02_scenario_3_completed_root_cannot_abort() -> None:
    """Scenario 3: A completed root with deferred dispatch cannot be aborted."""
    ledger = ConfigurableFaultLedger(fail_point="DURING_LATER")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED
    assert root_id in tx.completed_roots

    # In R1-B02, an aborted root could leak attestations; in Patch 4, completed root cannot abort
    with pytest.raises(ObservationError, match="Cannot ABORT already COMPLETED root"):
        tx.abort_exposure(root_id)

    # W remains committed and confirmations remain valid for completed root
    assert state.W.close_serial == 1
    assert ledger.accepted_confirmations == 2


def test_f01_02_scenario_4_post_commit_failure_readiness_barrier() -> None:
    """Scenario 4: Deferred outbox traps orchestration with OUTBOX_DELIVERY_PENDING."""
    ledger = ConfigurableFaultLedger(fail_point="BEFORE_PROCESSING")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED
    assert root_id in tx.completed_roots
    assert state.W.close_serial == 1
    assert ledger.delivery_attempts == 0
    assert ledger.accepted_confirmations == 0

    # Orchestration barrier prevents advancement
    with pytest.raises(ObservationError) as exc_info:
        tx.assert_outbox_ready(root_id)
    assert exc_info.value.code == StatusCode.OUTBOX_DELIVERY_PENDING


def test_f01_02_scenario_5_reconciliation_retry_and_idempotency() -> None:
    """Scenario 5: Explicit reconcile_outbox() completes delivery idempotently."""
    ledger = ConfigurableFaultLedger(fail_point="AFTER_FIRST")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    tx.end_exposure(root_id)
    assert ledger.delivery_attempts == 2
    assert ledger.accepted_confirmations == 1
    assert tx.has_pending_outbox(root_id) is True

    # Retry without fault via reconcile_outbox
    ledger.fail_point = "NONE"
    reconciled_count = tx.reconcile_outbox(root_id, ledger)
    assert reconciled_count == 2  # The remaining 2 unconfirmed notifications

    # Queue is now empty
    assert tx.has_pending_outbox(root_id) is False
    tx.assert_outbox_ready(root_id)  # Returns cleanly without raising

    # Total accepted confirmations is 3; idempotency prevented duplicate confirmations
    assert ledger.accepted_confirmations == 3
    assert len(ledger._rows_by_asm_gen) == 3
