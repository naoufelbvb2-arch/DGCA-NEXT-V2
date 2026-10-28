"""Forensic Investigation F01-02: OUTBOX_ATOMICITY_AND_FAILURE_INJECTION (R1-B02).

Investigates transaction atomicity and ordering between W publication and peripheral ledger consumption.
Normative contract: Peripheral attestations must never get ahead of legally committed W state.
"""

from __future__ import annotations

import pytest
from dgca.common.errors import ObservationError
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import Assembly, AssemblyStatus, MachineState, Region
from dgca.encoder.envelope import encode_exposure, encode_lexical_token_event
from dgca.experiments.gates import _extract_f0_cells, _wire_consolidated_synapse
from dgca.lifecycle.exposure_tx import ExposureStatus, ExposureTransactionManager
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1
from dgca.core.anatomy import SynapseScope


class FaultyReadoutLedger(SurfaceReadoutLedgerV1):
    """Diagnostic ledger with controlled fault injection at precise points."""

    def __init__(self, fail_point: str) -> None:
        super().__init__()
        self.fail_point = fail_point
        self.notifications_consumed = 0

    def consume_outbox_batch(self, batch: tuple[object, ...]) -> int:
        if self.fail_point == "BEFORE_PROCESSING":
            raise RuntimeError("FAULT_INJECTED: before notification processing")
        
        count = 0
        for notif in batch:
            super().consume_outbox_notification(notif)
            count += 1
            self.notifications_consumed += 1
            if self.fail_point == "AFTER_FIRST" and count == 1:
                raise RuntimeError("FAULT_INJECTED: after first notification")
            if self.fail_point == "DURING_LATER" and count == 2:
                raise RuntimeError("FAULT_INJECTED: during later notification")
        return count


def _setup_open_root_with_notifications(ledger: SurfaceReadoutLedgerV1) -> tuple[MachineState, ExposureTransactionManager, int]:
    state = MachineState()
    tx = ExposureTransactionManager(
        state,
        enable_context_pipeline=False,
        enable_assembly_pipeline=False,
        readout_ledger=ledger,
    )
    
    # Encode real events to extract genuine matching cells
    ev_a = encode_lexical_token_event("القط", exposure_id=1, event_order=0, boundary=True)
    ev_b = encode_lexical_token_event("يشرب", exposure_id=1, event_order=1, boundary=False)
    f0_cat = _extract_f0_cells(project_core_event_v1(ev_a.core_event))[:3]
    f0_drinks = _extract_f0_cells(project_core_event_v1(ev_b.core_event))[:3]

    # Pre-populate two live assemblies with matching cells so CoreCoverage >= 0.70
    asm1 = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(f0_cat),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    asm2 = Assembly(
        assembly_id=2,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(f0_drinks),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )
    state.W.assemblies[1] = asm1
    state.W.assemblies[2] = asm2
    for c in list(f0_cat) + list(f0_drinks):
        state.W.commit_cell(c, 0)
    for u in f0_cat:
        for v in f0_cat:
            if u != v:
                _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL)
    for u in f0_drinks:
        for v in f0_drinks:
            if u != v:
                _wire_consolidated_synapse(state, u, v, SynapseScope.LOCAL)

    # Process events with envelopes
    root_id = 1
    tx.begin_exposure(root_id)
    tx.process_event(ev_a.core_event, peripheral_envelope=ev_a.peripheral_surface)
    tx.process_event(ev_b.core_event, peripheral_envelope=ev_b.peripheral_surface)
    return state, tx, root_id


def test_f01_02_fault_point_1_before_processing() -> None:
    """Failure Point 1: Fault injected before notification processing."""
    ledger = FaultyReadoutLedger(fail_point="BEFORE_PROCESSING")
    state, tx, root_id = _setup_open_root_with_notifications(ledger)

    with pytest.raises(RuntimeError, match="before notification processing"):
        tx.end_exposure(root_id)

    # Root remains OPEN; W not committed; ledger has 0 notifications
    assert tx.status == ExposureStatus.OPEN
    assert root_id not in tx.completed_roots
    assert state.W.close_serial == 0
    assert ledger.notifications_consumed == 0


def test_f01_02_fault_point_2_after_first_notification() -> None:
    """Failure Point 2: Fault injected after 1st notification (atomicity violation confirmation)."""
    ledger = FaultyReadoutLedger(fail_point="AFTER_FIRST")
    state, tx, root_id = _setup_open_root_with_notifications(ledger)

    with pytest.raises(RuntimeError, match="after first notification"):
        tx.end_exposure(root_id)

    # Root remains OPEN; W was NOT committed
    assert tx.status == ExposureStatus.OPEN
    assert root_id not in tx.completed_roots
    assert state.W.close_serial == 0

    # CRITICAL INVARIANT VIOLATION (R1-B02):
    # Peripheral ledger consumed and stored the first notification even though root was never committed!
    assert ledger.notifications_consumed == 1
    assert len(ledger._rows_by_asm_gen) > 0, "Peripheral ledger leaked notification ahead of uncommitted W!"

    # Now abort the exposure
    tx.abort_exposure(root_id)
    assert tx.status == ExposureStatus.CLOSED
    # The aborted root left behind peripheral attestations in the ledger!
    assert len(ledger._rows_by_asm_gen) > 0


def test_f01_02_retry_after_failure_creates_duplicate_or_inconsistency() -> None:
    """Failure Point 5: Retry behavior after partial publication failure."""
    ledger = FaultyReadoutLedger(fail_point="AFTER_FIRST")
    state, tx, root_id = _setup_open_root_with_notifications(ledger)

    # First attempt fails mid-batch
    with pytest.raises(RuntimeError):
        tx.end_exposure(root_id)
    
    assert ledger.notifications_consumed == 1

    # Retry after failure
    ledger.fail_point = "NONE"
    rep = tx.end_exposure(root_id)
    assert rep.status == ExposureStatus.COMPLETED

    # Ledger received the first notification again during retry, total consumed = 3
    assert ledger.notifications_consumed == 3
