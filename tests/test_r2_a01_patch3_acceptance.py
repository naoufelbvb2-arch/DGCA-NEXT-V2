"""Acceptance test suite for R2-A01 Patch 3: Latent Topology Rollback on ABORT.

Normative references:
- DGCA_CORE_RC4_1.md §1.2, §1.3 (Latent Neighborhood & Co-active topology)
- DGCA_CORE_RC4_1.md §10.1 (Learning exposure lifecycle and FIFR-B06 LAB POLICY A)
- DGCA_LLA_RC4_1.md §7 (Atomic transaction rules: BEGIN, EVENT, END, ABORT)
- R2-A01-REMEDIATION-DESIGN-CONTRACT.md Section 6 (Patch 3: Latent Rollback)
- Acceptance scenarios: P4-01 through P4-05, failure safety gates, and scaling benchmarks.
"""

from __future__ import annotations

import dataclasses
from typing import Any
import pytest

from dgca.common.errors import ObservationError, StatusCode
from dgca.common.hashing import TOTAL_CELL_COUNT, Region
from dgca.core.latent_index import (
    COACTIVE_INTER_SLOTS,
    COACTIVE_INTRA_SLOTS,
    LatentNeighborhoodTable,
    WiringLogEntry,
)
from dgca.core.state import MachineState
from dgca.encoder import encode_exposure
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
)
from tests.test_r2_a01_patch2_acceptance import (
    canonical_state_digest,
    hash_state_snapshot,
)


def _snapshot_latent_table(table: LatentNeighborhoodTable) -> dict[str, Any]:
    """Capture 100% of internal state of LatentNeighborhoodTable into an immutable structure."""
    return {
        "_slots_by_cell": {
            cid: tuple(slots) for cid, slots in sorted(table._slots_by_cell.items())
        },
        "_pinned_slots": {
            cid: frozenset(pins) for cid, pins in sorted(table._pinned_slots.items()) if pins
        },
        "_coactive_reverse_index": {
            tgt: frozenset(srcs)
            for tgt, srcs in sorted(table._coactive_reverse_index.items())
            if srcs
        },
        "_wiring_logs": {
            cid: tuple(
                (e.event_clock, e.owner_cell_id, e.slot_index, e.old_target_id, e.new_target_id, e.reason)
                for e in entries
            )
            for cid, entries in sorted(table._wiring_logs.items())
        },
    }


def test_p4_01_abort_sensory_preservation():
    """P4-01: Abort Sensory Preservation (Core §10.1).

    Verifies:
    1. Root status transitions to ABORTED.
    2. Newly committed sensory cells remain in W.committed_cells with lawful metadata.
    3. The root high-watermark policy is preserved (watermark >= exposure_id).
    4. Root-local coactive topology is rolled back to BEGIN state.
    5. Newly committed sensory cells without physical slots have deterministic fixed
       neighbors accessible virtually via get_slots_read_only without allocating storage.
    """
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=True)

    # Initial state: no committed cells, empty latent table
    assert len(state.W.committed_cells) == 0
    assert len(state.W.latent_table._slots_by_cell) == 0

    snap_begin = _snapshot_latent_table(state.W.latent_table)
    hash_begin = hash_state_snapshot(snap_begin)

    # Start OPEN root 101 and process first lexical token ("القط")
    tx.begin_exposure(101)
    envelopes = encode_exposure("القط", exposure_id=101)
    assert len(envelopes) >= 1

    ev_result = tx.process_event(envelopes[0].core_event, peripheral_envelope=envelopes[0].peripheral_surface)
    new_sensory = set(ev_result.newly_committed_sensory_cells)
    assert len(new_sensory) > 0, "Expected lexical token to commit sensory cells"

    # Confirm sensory cells are committed and latent table was populated
    for cid in new_sensory:
        assert cid in state.W.committed_cells
    assert len(state.W.latent_table._slots_by_cell) > 0

    # ABORT exposure 101
    status = tx.abort_exposure(101)
    assert status == ExposureStatus.ABORTED

    # 1. Newly committed sensory cells remain committed (Core §10.1)
    for cid in new_sensory:
        assert cid in state.W.committed_cells
        assert isinstance(state.W.committed_cells[cid], int)
        assert state.W.committed_cells[cid] >= 0

    # 2. Watermark policy preserved
    assert state.W.completed_roots_high_watermark >= 101

    # 3. Latent table rolled back exactly to BEGIN snapshot
    snap_post_abort = _snapshot_latent_table(state.W.latent_table)
    hash_post_abort = hash_state_snapshot(snap_post_abort)
    assert snap_post_abort == snap_begin
    assert hash_post_abort == hash_begin
    assert len(state.W.latent_table._slots_by_cell) == 0

    # 4. Virtual lookup of retained sensory cells works deterministically without storage allocation
    sample_cell = next(iter(new_sensory))
    slots = state.W.latent_table.get_slots_read_only(sample_cell)
    assert len(slots) == 24
    # Fixed local (slots 6..11) and topographic (slots 18..23) are valid integers
    for idx in range(6, 12):
        assert isinstance(slots[idx], int)
    for idx in range(18, 24):
        assert isinstance(slots[idx], int)
    # Virtual lookup did not mutate internal table
    assert len(state.W.latent_table._slots_by_cell) == 0


def test_p4_02_abort_coactive_latent_slot_rollback():
    """P4-02: Abort Coactive Latent Slot Rollback.

    Verifies:
    1. Produces >= 100 actual coactive assignment and recycling mutations in an OPEN root.
    2. ABORT restores all 24 slot positions across all previously materialized cells.
    3. Materialized key set, values, and SHA-256 digests match BEGIN exactly.
    """
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=False)

    # Pre-populate 50 materialized cells in the latent table with initial wiring
    table = state.W.latent_table
    pre_materialized = list(range(100, 150))
    for cid in pre_materialized:
        table.materialize_cell(cid)
        # Wire slot 0 to (cid + 1)
        table._set_coactive_slot(cid, 0, (cid + 1) % TOTAL_CELL_COUNT, event_clock=10, reason="PRE_POP")

    snap_begin = _snapshot_latent_table(table)
    hash_begin = hash_state_snapshot(snap_begin)
    assert len(table._slots_by_cell) == 50

    # Begin exposure 201
    tx.begin_exposure(201)

    # Produce at least 100 genuine coactive assignment / recycling mutations
    mutation_count = 0
    # 1. 50 assignments in intra slot 1
    for cid in pre_materialized:
        old_val = table._slots_by_cell[cid][1]
        new_val = (cid + 2) % TOTAL_CELL_COUNT
        assert old_val != new_val
        table._set_coactive_slot(cid, 1, new_val, event_clock=20, reason="ADMIT_SLOT_1")
        mutation_count += 1

    # 2. 50 assignments in inter slot 12
    for cid in pre_materialized:
        old_val = table._slots_by_cell[cid][12]
        new_val = (cid + 1000) % TOTAL_CELL_COUNT
        assert old_val != new_val
        table._set_coactive_slot(cid, 12, new_val, event_clock=21, reason="ADMIT_SLOT_12")
        mutation_count += 1

    # 3. 20 recycling mutations in intra slot 0
    for cid in pre_materialized[:20]:
        old_val = table._slots_by_cell[cid][0]
        recycled_val = (cid + 500) % TOTAL_CELL_COUNT
        assert old_val != recycled_val
        table._set_coactive_slot(cid, 0, recycled_val, event_clock=22, reason="RECYCLE_SLOT_0")
        mutation_count += 1

    assert mutation_count >= 120, f"Expected >= 100 mutations, got {mutation_count}"

    # Verify table has diverged from BEGIN
    snap_mutated = _snapshot_latent_table(table)
    assert snap_mutated != snap_begin
    assert hash_state_snapshot(snap_mutated) != hash_begin

    # ABORT exposure 201
    status = tx.abort_exposure(201)
    assert status == ExposureStatus.ABORTED

    # Assert exact restoration across all 24 slot positions and all materialized cells
    snap_restored = _snapshot_latent_table(state.W.latent_table)
    hash_restored = hash_state_snapshot(snap_restored)

    assert set(state.W.latent_table._slots_by_cell.keys()) == set(pre_materialized)
    for cid in pre_materialized:
        assert state.W.latent_table._slots_by_cell[cid] == list(snap_begin["_slots_by_cell"][cid])

    assert snap_restored == snap_begin
    assert hash_restored == hash_begin


def test_p4_03_reverse_index_symmetry():
    """P4-03: Reverse-Index Symmetry & Audit Log Rollback.

    Verifies:
    1. Genuine coactive assignments modify _coactive_reverse_index, _pinned_slots, and _wiring_logs.
    2. ABORT restores reverse index, pins, and audit logs with zero orphan entries.
    3. Forward/reverse neighborhood symmetry holds identically to BEGIN.
    """
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=False)
    table = state.W.latent_table

    # Set up initial topology: cell 500 wires to cell 600
    table.materialize_cell(500)
    table.materialize_cell(600)
    table._set_coactive_slot(500, 0, 600, event_clock=1, reason="INITIAL")
    table._pinned_slots.setdefault((500, 0), set()).add(1)

    snap_begin = _snapshot_latent_table(table)
    hash_begin = hash_state_snapshot(snap_begin)

    # Initial symmetry check: 600 in forward(500) <==> 500 in reverse(600)
    assert 600 in table.forward_neighbors(500)
    assert 500 in table.reverse_neighbors(600)

    # Begin exposure 301
    tx.begin_exposure(301)

    # Add 10 new coactive links targeting cell 700 and pin them
    table.materialize_cell(700)
    for i in range(10):
        src = 501 + i
        table.materialize_cell(src)
        table._set_coactive_slot(src, 2, 700, event_clock=100 + i, reason="OPEN_ROOT_LINK")
        table._pinned_slots.setdefault((src, 2), set()).add(100 + i)

    # Verify reverse index was populated with new target
    assert 700 in table._coactive_reverse_index
    assert len(table._coactive_reverse_index[700]) == 10
    for i in range(10):
        src = 501 + i
        assert 700 in table.forward_neighbors(src)
        assert src in table.reverse_neighbors(700)
        assert table.is_slot_pinned(src, 2)

    # ABORT exposure 301
    status = tx.abort_exposure(301)
    assert status == ExposureStatus.ABORTED

    # Verify exact reverse-index restoration
    snap_post = _snapshot_latent_table(state.W.latent_table)
    assert snap_post == snap_begin
    assert hash_state_snapshot(snap_post) == hash_begin

    # Zero orphan reverse-index entries
    assert 700 not in state.W.latent_table._coactive_reverse_index
    assert 600 in state.W.latent_table._coactive_reverse_index
    assert state.W.latent_table._coactive_reverse_index[600] == {500}

    # Symmetry preserved
    assert 600 in state.W.latent_table.forward_neighbors(500)
    assert 500 in state.W.latent_table.reverse_neighbors(600)

    # Pins and logs restored
    assert state.W.latent_table.is_slot_pinned(500, 0)
    for i in range(10):
        src = 501 + i
        assert not state.W.latent_table.is_slot_pinned(src, 2)
        assert len(state.W.latent_table.get_wiring_log(src)) == 0


def test_p4_04_duplicate_abort_idempotency():
    """P4-04: Duplicate ABORT Idempotency.

    Verifies:
    1. Calling abort_exposure multiple times on an already aborted root returns ABORTED.
    2. No secondary rollback or state mutation occurs.
    3. Duplicate ABORT of an earlier root after a subsequent root commits leaves the
       subsequent root's topology completely unaffected.
    """
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=False)
    table = state.W.latent_table

    # Root 401
    tx.begin_exposure(401)
    table.materialize_cell(10)
    table._set_coactive_slot(10, 0, 20, event_clock=1, reason="R401")

    # First ABORT
    status1 = tx.abort_exposure(401)
    assert status1 == ExposureStatus.ABORTED
    snap_after_abort1 = _snapshot_latent_table(state.W.latent_table)
    hash_after_abort1 = hash_state_snapshot(snap_after_abort1)

    # Second ABORT (immediate duplicate)
    status2 = tx.abort_exposure(401)
    assert status2 == ExposureStatus.ABORTED
    snap_after_abort2 = _snapshot_latent_table(state.W.latent_table)
    assert snap_after_abort2 == snap_after_abort1
    assert hash_state_snapshot(snap_after_abort2) == hash_after_abort1

    # Now begin and complete Root 402 with legitimate topology
    tx.begin_exposure(402)
    state.W.latent_table.materialize_cell(30)
    state.W.latent_table._set_coactive_slot(30, 0, 40, event_clock=5, reason="R402")
    envelopes_402 = encode_exposure("ماء", exposure_id=402)
    for env in envelopes_402:
        tx.process_event(env.core_event, peripheral_envelope=env.peripheral_surface)
    rep_402 = tx.end_exposure(402)
    assert rep_402.status == ExposureStatus.COMPLETED

    snap_after_r402 = _snapshot_latent_table(state.W.latent_table)
    hash_after_r402 = hash_state_snapshot(snap_after_r402)
    assert 30 in state.W.latent_table._slots_by_cell

    # Third ABORT for Root 401 (stale duplicate after later root committed)
    status3 = tx.abort_exposure(401)
    assert status3 == ExposureStatus.ABORTED

    # Root 402 topology is 100% unaffected
    snap_after_stale_abort = _snapshot_latent_table(state.W.latent_table)
    assert snap_after_stale_abort == snap_after_r402
    assert hash_state_snapshot(snap_after_stale_abort) == hash_after_r402


def test_p4_05_multi_root_isolation():
    """P4-05: Multi-Root Isolation: Root 1 (COMPLETE) -> Root 2 (COMPLETE) -> Root 3 (ABORT) -> Root 4 (COMPLETE).

    Verifies:
    1. Root 1 topology survives.
    2. Root 2 topology survives.
    3. Root 3 root-local topology is completely rolled back.
    4. Root 4 learns from a lawful post-Root-2 state.
    5. Repeating ABORT for Root 3 does not corrupt Root 4.
    """
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=True)

    # Root 1 (COMPLETE): "القط"
    tx.begin_exposure(1)
    env1 = encode_exposure("القط", exposure_id=1)
    for e in env1:
        tx.process_event(e.core_event, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(1)
    snap_r1 = _snapshot_latent_table(state.W.latent_table)

    # Root 2 (COMPLETE): "يشرب"
    tx.begin_exposure(2)
    env2 = encode_exposure("يشرب", exposure_id=2)
    for e in env2:
        tx.process_event(e.core_event, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(2)
    snap_r2 = _snapshot_latent_table(state.W.latent_table)
    hash_r2 = hash_state_snapshot(snap_r2)

    # Root 3 (ABORT): "حليب" + manual coactive injection
    tx.begin_exposure(3)
    env3 = encode_exposure("حليب", exposure_id=3)
    for e in env3:
        tx.process_event(e.core_event, peripheral_envelope=e.peripheral_surface)
    # Inject coactive link during Root 3 OPEN
    state.W.latent_table.materialize_cell(999)
    state.W.latent_table._set_coactive_slot(999, 0, 888, event_clock=99, reason="R3_INJECT")
    assert 999 in state.W.latent_table._slots_by_cell

    # ABORT Root 3
    tx.abort_exposure(3)
    snap_post_r3_abort = _snapshot_latent_table(state.W.latent_table)
    hash_post_r3_abort = hash_state_snapshot(snap_post_r3_abort)

    # Invariance check: state after Root 3 ABORT is identical to state after Root 2 END!
    assert snap_post_r3_abort == snap_r2
    assert hash_post_r3_abort == hash_r2
    assert 999 not in state.W.latent_table._slots_by_cell

    # Root 4 (COMPLETE): "ماء"
    tx.begin_exposure(4)
    env4 = encode_exposure("ماء", exposure_id=4)
    for e in env4:
        tx.process_event(e.core_event, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(4)
    snap_r4 = _snapshot_latent_table(state.W.latent_table)
    hash_r4 = hash_state_snapshot(snap_r4)

    # Re-call ABORT for Root 3
    status_repeat = tx.abort_exposure(3)
    assert status_repeat == ExposureStatus.ABORTED

    # Root 4 state remains 100% intact
    snap_post_repeat = _snapshot_latent_table(state.W.latent_table)
    assert snap_post_repeat == snap_r4
    assert hash_state_snapshot(snap_post_repeat) == hash_r4


def test_p4_06_failure_and_rollback_safety():
    """Negative and safety edge-case verification for Patch 3 (Section 7).

    Covers:
    - Repeated BEGIN on same OPEN root (returns journal without overwriting snapshot).
    - ABORT after multiple legal events.
    - ABORT following partial coactive recycling.
    - ABORT with no successful coactive changes.
    - ABORT after a rejected event (e.g. invalid event order).
    - ABORT of an already completed root raises ObservationError.
    - Duplicate ABORT after later root committed.
    """
    state = MachineState()
    tx = ExposureTransactionManager(state, auto_coactive_latent=False)

    # 1. Repeated BEGIN on same OPEN root
    j1 = tx.begin_exposure(10)
    snap_initial = _snapshot_latent_table(state.W.latent_table)
    j2 = tx.begin_exposure(10)
    assert j1 is j2
    assert j2.latent_table_begin is not None

    # 2. ABORT with zero events/coactive changes
    status = tx.abort_exposure(10)
    assert status == ExposureStatus.ABORTED
    assert _snapshot_latent_table(state.W.latent_table) == snap_initial

    # 3. ABORT of an already completed root raises ObservationError
    tx.begin_exposure(11)
    env11 = encode_exposure("ماء", exposure_id=11)
    for e in env11:
        tx.process_event(e.core_event, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(11)
    assert 11 in tx.completed_roots
    with pytest.raises(ObservationError, match="Cannot ABORT already COMPLETED root"):
        tx.abort_exposure(11)

    # 4. ABORT following partial coactive recycling
    tx.begin_exposure(12)
    state.W.latent_table.materialize_cell(50)
    state.W.latent_table._set_coactive_slot(50, 0, 60, event_clock=1, reason="FIRST")
    env12 = encode_exposure("ماء", exposure_id=12)
    for e in env12:
        tx.process_event(e.core_event, peripheral_envelope=e.peripheral_surface)
    tx.end_exposure(12)
    snap_pre_recycle = _snapshot_latent_table(state.W.latent_table)

    # Second root 13 opens, recycles slot 0 to 70, then aborts
    tx.begin_exposure(13)
    state.W.latent_table._set_coactive_slot(50, 0, 70, event_clock=2, reason="RECYCLE")
    assert state.W.latent_table._slots_by_cell[50][0] == 70
    tx.abort_exposure(13)

    # Restored to pre-recycle state
    assert state.W.latent_table._slots_by_cell[50][0] == 60
    assert 70 not in state.W.latent_table._coactive_reverse_index
    assert 60 in state.W.latent_table._coactive_reverse_index

    # 5. ABORT after rejected event (e.g. non-contiguous event order)
    snap_pre_14 = _snapshot_latent_table(state.W.latent_table)
    tx.begin_exposure(14)
    state.W.latent_table.materialize_cell(80)
    state.W.latent_table._set_coactive_slot(80, 0, 90, event_clock=10, reason="PROV")

    # Construct invalid event (event_order=5 instead of 0)
    valid_env = encode_exposure("القط", exposure_id=14)[0]
    bad_core = dataclasses.replace(valid_env.core_event, event_order=5)

    with pytest.raises(ObservationError, match="Out-of-order event_order"):
        tx.process_event(bad_core, peripheral_envelope=valid_env.peripheral_surface)

    # After error, root is still OPEN; calling abort rolls back all prior mutations
    tx.abort_exposure(14)
    assert _snapshot_latent_table(state.W.latent_table) == snap_pre_14
    assert 80 not in state.W.latent_table._slots_by_cell


def test_p4_07_scaling_and_memory_sanity():
    """Verify scaling and memory sanity across 50 consecutive BEGIN -> OPEN -> ABORT cycles (Section 8)."""
    import gc
    gc.collect()

    state = MachineState()
    for cid in range(300):
        state.W.latent_table.materialize_cell(cid)
        if cid > 0:
            state.W.latent_table._set_coactive_slot(cid, 0, cid - 1, event_clock=1, reason="INIT")

    snap_initial = _snapshot_latent_table(state.W.latent_table)
    initial_cells = len(state.W.latent_table._slots_by_cell)
    initial_rev = len(state.W.latent_table._coactive_reverse_index)

    tx = ExposureTransactionManager(state, auto_coactive_latent=False)

    for i in range(1, 51):
        tx.begin_exposure(1000 + i)
        # Mutate coactive links
        t0 = (i % 290) + 5
        t1 = ((i + 1) % 290) + 5
        state.W.latent_table._set_coactive_slot(0, 1, t0, event_clock=i, reason="STRESS")
        state.W.latent_table._set_coactive_slot(1, 1, t1, event_clock=i, reason="STRESS")
        status = tx.abort_exposure(1000 + i)
        assert status == ExposureStatus.ABORTED

    gc.collect()

    # Zero latent topology drift after 50 cycles
    assert len(state.W.latent_table._slots_by_cell) == initial_cells
    assert len(state.W.latent_table._coactive_reverse_index) == initial_rev
    assert _snapshot_latent_table(state.W.latent_table) == snap_initial

