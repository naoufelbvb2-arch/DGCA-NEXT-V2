"""Forensic Investigation F01-02: OUTBOX_ATOMICITY_AND_FAILURE_INJECTION (R1-B02 & Task 7).

Complete fault injection and atomicity scenario coverage:
1. Failure before notification processing.
2. Failure after the first notification.
3. Failure during processing of a later notification in a multi-item batch.
4. Failure immediately before W publication (after outbox batch consumed).
5. Recovery/retry after each failure scenario.
6. Distinction between duplicate notification delivery attempts and duplicate accepted confirmations.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import ObservationError
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
            raise RuntimeError("FAULT: immediately before W publication")
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


def test_f01_02_scenario_1_failure_before_processing() -> None:
    """Scenario 1: Fault injected before notification processing."""
    ledger = ConfigurableFaultLedger(fail_point="BEFORE_PROCESSING")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    with pytest.raises(RuntimeError, match="before notification processing"):
        tx.end_exposure(root_id)

    assert tx.status == ExposureStatus.OPEN
    assert root_id not in tx.completed_roots
    assert state.W.close_serial == 0
    assert ledger.delivery_attempts == 0
    assert ledger.accepted_confirmations == 0


def test_f01_02_scenario_2_failure_after_first_notification() -> None:
    """Scenario 2: Fault injected after 1st notification (partial batch failure)."""
    ledger = ConfigurableFaultLedger(fail_point="AFTER_FIRST")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    with pytest.raises(RuntimeError, match="after first notification"):
        tx.end_exposure(root_id)

    # Root remains OPEN; W uncommitted
    assert tx.status == ExposureStatus.OPEN
    assert state.W.close_serial == 0
    # Ledger leaked partial attestation: 1 accepted confirmation for an uncommitted root!
    assert ledger.accepted_confirmations == 1
    assert len(ledger._rows_by_asm_gen) > 0


def test_f01_02_scenario_3_failure_during_later_notification() -> None:
    """Scenario 3: Fault injected during later notification (at idx=2 of 3)."""
    ledger = ConfigurableFaultLedger(fail_point="DURING_LATER")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    with pytest.raises(RuntimeError, match="during later notification"):
        tx.end_exposure(root_id)

    assert tx.status == ExposureStatus.OPEN
    assert state.W.close_serial == 0
    # Two notifications were delivered and accepted before the third failed!
    assert ledger.delivery_attempts == 3
    assert ledger.accepted_confirmations == 2

    # If aborted, those 2 confirmations survive in ledger
    tx.abort_exposure(root_id)
    assert tx.status == ExposureStatus.CLOSED
    assert ledger.accepted_confirmations == 2, "Partial attestations leaked into ledger from aborted root"


def test_f01_02_scenario_4_failure_immediately_before_w_publication() -> None:
    """Scenario 4: Fault injected after all notifications consumed, right before W swap."""
    ledger = ConfigurableFaultLedger(fail_point="BEFORE_W_PUBLICATION")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    with pytest.raises(RuntimeError, match="immediately before W publication"):
        tx.end_exposure(root_id)

    # Root remains OPEN; W uncommitted
    assert tx.status == ExposureStatus.OPEN
    assert state.W.close_serial == 0
    # ALL 3 notifications were consumed and accepted by the peripheral ledger!
    assert ledger.accepted_confirmations == 3
    assert len(ledger._rows_by_asm_gen) == 3


def test_f01_02_scenario_5_recovery_retry_duplicate_attempts_vs_accepted() -> None:
    """Scenario 5: Recovery retry distinguishing delivery attempts from accepted confirmations."""
    ledger = ConfigurableFaultLedger(fail_point="BEFORE_W_PUBLICATION")
    state, tx, root_id = _setup_open_root_with_three_assemblies(ledger)

    # First attempt fails right before W commit; all 3 notifications accepted by ledger
    with pytest.raises(RuntimeError):
        tx.end_exposure(root_id)
    
    assert ledger.delivery_attempts == 3
    assert ledger.accepted_confirmations == 3

    # Retry without fault
    ledger.fail_point = "NONE"
    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED

    # On retry:
    # 3 duplicate delivery attempts occurred (total attempts = 6)
    # BUT accepted confirmations remained 3 because idempotency rejected duplicate roots!
    assert ledger.delivery_attempts == 6
    assert ledger.accepted_confirmations == 3, "Idempotency correctly prevented duplicate confirmations"
