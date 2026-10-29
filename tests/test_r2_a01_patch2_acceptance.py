"""Acceptance test suite for R2-A01 Patch 2: Read-Only Immutability, Latent Virtual Lookups & Transactional STALE.

Covers:
- P1-01: Complete RETRIEVE Immutability Gate (Full WState, HSlowState, RState snapshots)
- P1-02: Stale Binding Read-Only Isolation (Status stays ACTIVE in caller W, gate closes, diagnostic returned)
- P1-03: Homeostasis Scratch Isolation (H_slow cloned in scratch, float equality across repeated runs)
- P1-04: Transactional STALE Transition (Abort leaves ACTIVE, Commit settles to STALE on w_shadow)
- Focused latent tests: Virtual lookups on unmaterialized cells, forward/reverse neighbor and eligibility immutability
- Focused generation tests: GENERATE mode leaves caller permanent state and ledger completely untouched
- Mode discrimination: LEARN mode updates last_referenced_event, RETRIEVE mode does not
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any
import pytest

from dgca.common.errors import DGCAError, StatusCode
from dgca.common.hashing import Region, WitnessSourceKind
from dgca.common.numeric import q6_from_binary64
from dgca.core.anatomy import (
    Synapse,
    SynapseKey,
    SynapseScope,
    SynapseState,
)
from dgca.core.context_gate import validate_and_refresh_stable_binding
from dgca.core.dynamics import execute_two_pass_event
from dgca.core.generator import generate_episode
from dgca.core.latent_index import (
    TOTAL_CELL_COUNT,
    LatentNeighborhoodTable,
    compute_fixed_local_neighbors,
    compute_fixed_topographic_neighbors,
)
from dgca.core.sic_v1 import project_core_event_v1
from dgca.core.state import (
    Assembly,
    AssemblyStatus,
    BindingStatus,
    ExecutionMode,
    HSlowState,
    MachineState,
    RState,
    StableBinding,
    WState,
)
from dgca.encoder.envelope import (
    CoreEventPayloadV1,
    EventOrigin,
    Marker,
    PeripheralSurfaceEnvelopeV1,
    encode_lexical_token_event,
)
from dgca.lifecycle.exposure_tx import (
    ExposureStatus,
    ExposureTransactionManager,
    compute_pred_score,
    run_read_only_episode,
)
from dgca.peripheral.readout_ledger import SurfaceReadoutLedgerV1


# ---------------------------------------------------------------------------
# Deep Snapshot Helpers for Invariant Verification
# ---------------------------------------------------------------------------

def snapshot_w(w: WState) -> dict[str, Any]:
    """Capture a comprehensive deep snapshot of WState covering all physical state fields."""
    return {
        "committed_cells": dict(w.committed_cells),
        "last_referenced_event": dict(w.last_referenced_event),
        "synapses": {
            k: (
                s.key,
                s.state,
                s.S,
                s.E_ext,
                s.E_int,
                s.external_count,
                tuple(sorted(s.confirmed_roots)),
            )
            for k, s in sorted(w.synapses.items())
        },
        "latent_table_slots": {
            cid: tuple(slots) for cid, slots in sorted(w.latent_table._slots_by_cell.items())
        },
        "latent_table_pinned": {
            cid: set(slots) for cid, slots in sorted(w.latent_table._pinned_slots.items())
        },
        "latent_table_reverse": {
            cid: set(sources) for cid, sources in sorted(w.latent_table._coactive_reverse_index.items())
        },
        "latent_table_logs": {
            cid: tuple(
                (e.event_clock, e.owner_cell_id, e.slot_index, e.old_target_id, e.new_target_id, e.reason)
                for e in entries
            )
            for cid, entries in sorted(w.latent_table._wiring_logs.items())
        },
        "reserved_keys": {
            cid: set(keys) for cid, keys in sorted(w.reserved_keys_by_candidate.items())
        },
        "assemblies": {
            aid: (
                asm.assembly_id,
                asm.region,
                tuple(sorted(asm.member_cell_ids)),
                asm.structural_generation,
                asm.status,
            )
            for aid, asm in sorted(w.assemblies.items())
        },
        "assemblies_by_member": {
            cid: set(aids) for cid, aids in sorted(w.assemblies_by_member.items())
        },
        "stable_bindings": {
            zid: (
                b.z_cell_id,
                b.anchor_id,
                b.owner_seq,
                b.binding_generation,
                b.p_keys,
                b.c_keys,
                b.y_keys,
                tuple(sorted(b.anchor_source_set)),
                b.l_z_q6,
                b.u_z_q6,
                b.tau_ctx_q6,
                b.status,
            )
            for zid, b in sorted(w.stable_bindings.items())
        },
        "global_event_clock": w.global_event_clock,
        "completed_roots_high_watermark": w.completed_roots_high_watermark,
        "completed_external_events_count": w.completed_external_events_count,
        "close_serial": w.close_serial,
    }


def snapshot_h_slow(h: HSlowState) -> dict[str, Any]:
    """Capture a comprehensive snapshot of HSlowState homeostatic variables."""
    return {
        "r_bar": dict(h.r_bar),
        "g": dict(h.g),
        "rho_bar": dict(h.rho_bar_by_region),
        "theta_active": dict(h.theta_active_by_region),
    }


def snapshot_r(r: RState) -> dict[str, Any]:
    """Capture a snapshot of caller RState."""
    return {
        "A": dict(r.A),
        "A_prev": dict(r.A_prev),
        "A_pass1": dict(r.A_pass1),
        "A_hist": dict(r.A_hist),
        "F_step": set(r.F_step),
        "F_step_prev": set(r.F_step_prev),
        "step_index": r.step_index,
    }


def snapshot_ledger(ledger: SurfaceReadoutLedgerV1) -> dict[str, Any]:
    """Capture a snapshot of SurfaceReadoutLedgerV1."""
    return {
        "rows": {
            k: (row.assembly_id, row.structural_generation, row.surface_sha256, row.surface_text, row.feature_bundle_digest, tuple(sorted(row.confirmed_roots)))
            for k, row in sorted(ledger._rows_by_asm_gen.items())
        },
        "bundles": dict(ledger._bundles_by_surface),
        "processed_outbox": set(ledger._processed_outbox_keys),
    }


# ---------------------------------------------------------------------------
# Trained Network Fixture Builder
# ---------------------------------------------------------------------------

def _build_rich_test_state() -> tuple[MachineState, CoreEventPayloadV1, CoreEventPayloadV1, int]:
    """Build a rich, verified network state with committed cells, consolidated synapses, and StableBinding."""
    state = MachineState()

    ev_a = encode_lexical_token_event("القط", exposure_id=1, event_order=0).core_event
    ev_b = encode_lexical_token_event("يشرب", exposure_id=1, event_order=1).core_event
    ev_c = encode_lexical_token_event("حليب", exposure_id=1, event_order=2).core_event

    proj_a = project_core_event_v1(ev_a)
    proj_b = project_core_event_v1(ev_b)
    proj_c = project_core_event_v1(ev_c)

    p_a = tuple(sorted(proj_a.x_fixed_by_global_id.keys()))[:2]
    c_b = tuple(sorted(proj_b.x_fixed_by_global_id.keys()))[:2]
    y_c = tuple(sorted(proj_c.x_fixed_by_global_id.keys()))[:3]

    for cid in p_a + c_b + y_c:
        state.W.commit_cell(cid, 0)

    # Pick candidate z from uncommitted cells in LANGUAGE region
    free_cells = [
        c for c in range(100, 200)
        if c not in state.W.committed_cells
    ]
    z_cell = free_cells[0]
    state.W.commit_cell(z_cell, 0)

    def _wire_syn(src: int, tgt: int, scope: SynapseScope, s_val: float = 0.85):
        if not state.W.latent_table.is_eligible(src, tgt):
            try:
                state.W.latent_table.admit_or_recycle_coactive_partner(
                    src, tgt,
                    protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(src),
                    event_clock=state.W.global_event_clock,
                    reason="TEST_FIXTURE",
                )
            except Exception:
                state.W.latent_table.admit_or_recycle_coactive_partner(
                    tgt, src,
                    protected_bidirectional_neighbors=state.W.get_protected_bidirectional_neighbors(tgt),
                    event_clock=state.W.global_event_clock,
                    reason="TEST_FIXTURE",
                )
        syn = Synapse(
            key=(src, tgt, scope),
            state=SynapseState.CONSOLIDATED,
            S=s_val,
            E_ext=4.0,
            E_int=0.0,
            external_count=3,
            confirmed_roots=(1, 2, 3),
        )
        state.W.add_or_replace_synapse(syn)

    # Wire P -> z, C -> z, z -> Y
    for p in p_a:
        _wire_syn(p, z_cell, SynapseScope.ASSOCIATIVE, 0.90)
    for b in c_b:
        _wire_syn(b, z_cell, SynapseScope.LOCAL, 0.90)
    for y in y_c:
        _wire_syn(z_cell, y, SynapseScope.ASSOCIATIVE, 0.95)

    # Register calibrated StableBinding
    anchor_set_b = frozenset(proj_b.x_fixed_by_global_id.keys())
    state.W.stable_bindings[z_cell] = StableBinding(
        schema_version=2,
        z_cell_id=z_cell,
        anchor_id=c_b[0],
        owner_seq=1,
        binding_generation=1,
        p_keys=((p_a[0], z_cell, SynapseScope.ASSOCIATIVE), (p_a[1], z_cell, SynapseScope.ASSOCIATIVE)),
        l_z_q6=500_000,
        u_z_q6=100_000,
        tau_ctx_q6=150_000,
        c_keys=((c_b[0], z_cell, SynapseScope.LOCAL), (c_b[1], z_cell, SynapseScope.LOCAL)),
        y_keys=((z_cell, y_c[0], SynapseScope.ASSOCIATIVE), (z_cell, y_c[1], SynapseScope.ASSOCIATIVE)),
        anchor_source_set=anchor_set_b,
        status=BindingStatus.ACTIVE,
        depth=1,
    )

    # Wire reciprocal triangle for Assembly on y_c
    for u in y_c:
        for v in y_c:
            if u != v:
                _wire_syn(u, v, SynapseScope.LOCAL, 0.80)

    state.W.assemblies[1] = Assembly(
        assembly_id=1,
        region=Region.LANGUAGE,
        member_cell_ids=frozenset(y_c),
        structural_generation=1,
        status=AssemblyStatus.LIVE,
    )

    return state, ev_a, ev_b, z_cell


# ===========================================================================
# 1. Mandatory Acceptance Tests (P1-01 through P1-04)
# ===========================================================================

def test_p1_01_complete_retrieve_immutability_gate():
    """Verify complete state immutability across read-only episode (W_after == W_before, H_slow, R).

    Specifically verifies:
    - w.last_referenced_event is NOT updated in RETRIEVE mode
    - latent_table._slots_by_cell is NOT populated for unmaterialized cells
    - synaptic weights, assemblies, bindings, and counters remain bit-for-bit identical
    """
    state, ev_a, ev_b, z_cell = _build_rich_test_state()

    # Pre-snapshot entire state
    w_snap_before = snapshot_w(state.W)
    h_snap_before = snapshot_h_slow(state.H_slow)
    r_snap_before = snapshot_r(state.R)
    latent_keys_before = set(state.W.latent_table._slots_by_cell.keys())
    last_ref_before = dict(state.W.last_referenced_event)

    # Execute read-only episode
    summary = run_read_only_episode(state, [ev_a, ev_b])

    # Assert active cells fired during episode (computation actually occurred)
    assert len(summary.event_results) == 2
    assert len(summary.event_results[0].f_step) > 0
    assert len(summary.event_results[1].f_step) > 0

    # Post-snapshots
    w_snap_after = snapshot_w(state.W)
    h_snap_after = snapshot_h_slow(state.H_slow)
    r_snap_after = snapshot_r(state.R)

    # Exact equality checks
    assert w_snap_after == w_snap_before, "WState mutated during read-only episode!"
    assert h_snap_after == h_snap_before, "HSlowState mutated during read-only episode!"
    assert r_snap_after == r_snap_before, "Caller RState mutated during read-only episode!"

    # Specific defect verifications
    assert state.W.last_referenced_event == last_ref_before, "last_referenced_event modified in RETRIEVE!"
    assert set(state.W.latent_table._slots_by_cell.keys()) == latent_keys_before, "Latent table keys expanded!"


def test_p1_02_stale_binding_read_only_isolation():
    """Verify that encountered invalid bindings in read-only mode close the gate without mutating status to STALE."""
    state, ev_a, ev_b, z_cell = _build_rich_test_state()

    # Corrupt binding calibration: l_z_q6 > u_z_q6 violates mandatory calibration invariant
    bad_binding = dataclasses.replace(
        state.W.stable_bindings[z_cell],
        l_z_q6=100_000,
        u_z_q6=500_000,  # Invalid: l_z_q6 must be >= u_z_q6
    )
    state.W.stable_bindings[z_cell] = bad_binding

    w_snap_before = snapshot_w(state.W)

    # Run read-only episode
    summary = run_read_only_episode(state, [ev_a, ev_b])

    # 1. Gate must close for z_cell
    ev1_res = summary.event_results[1]
    assert ev1_res.g_ctx_by_z.get(z_cell, 0) == 0, "Gate should be closed for invalid binding!"

    # 2. Diagnostic must record invalid context threshold
    assert StatusCode.INVALID_CONTEXT_THRESHOLD in ev1_res.diagnostics

    # 3. Permanent caller W must NOT mutate binding status to STALE
    assert state.W.stable_bindings[z_cell].status == BindingStatus.ACTIVE, "Binding status mutated to STALE in RETRIEVE!"

    # 4. Total WState immutability
    w_snap_after = snapshot_w(state.W)
    assert w_snap_after == w_snap_before, "WState snapshot changed despite read-only mode!"


def test_p1_03_homeostasis_scratch_isolation():
    """Verify homeostatic slow variables H_slow remain strictly isolated in scratch and deterministic across runs."""
    state, ev_a, ev_b, _ = _build_rich_test_state()

    h_snap_initial = snapshot_h_slow(state.H_slow)

    # Run multiple read-only episodes
    outputs = []
    for run_idx in range(5):
        summary = run_read_only_episode(state, [ev_a, ev_b])
        outputs.append(summary.next_step_pt_by_cell)
        h_snap_current = snapshot_h_slow(state.H_slow)
        assert h_snap_current == h_snap_initial, f"H_slow mutated on run {run_idx}!"

    # Output determinism check: every run produces identical floating-point temporal drive
    for out in outputs[1:]:
        assert out == outputs[0], "Non-deterministic output across read-only episodes!"


def test_p1_04_transactional_stale_transition_abort_vs_commit():
    """Verify transactional STALE mechanics: ABORT preserves ACTIVE, COMMIT settles invalid binding to STALE."""
    # --- Case A: Aborted Exposure preserves ACTIVE on permanent W ---
    state_a, _, _, z_cell = _build_rich_test_state()
    # Create events matching exposure_id 101
    ev_a101 = encode_lexical_token_event("القط", exposure_id=101, event_order=0).core_event
    ev_b101 = encode_lexical_token_event("يشرب", exposure_id=101, event_order=1).core_event

    # Corrupt binding on state_a
    state_a.W.stable_bindings[z_cell] = dataclasses.replace(
        state_a.W.stable_bindings[z_cell],
        l_z_q6=100_000,
        u_z_q6=500_000,
    )
    tx_a = ExposureTransactionManager(state_a, allow_headless_events=True)
    tx_a.begin_exposure(101)
    tx_a.process_event(ev_a101)
    tx_a.process_event(ev_b101)
    abort_status = tx_a.abort_exposure(101)

    assert abort_status == ExposureStatus.ABORTED
    assert state_a.W.stable_bindings[z_cell].status == BindingStatus.ACTIVE, "Aborted transaction marked binding STALE on permanent state!"

    # --- Case B: Committed Exposure settles invalid binding to STALE on shadow W (Step 5.1) ---
    state_b, _, _, z_cell = _build_rich_test_state()
    # Create events matching exposure_id 102
    ev_a102 = encode_lexical_token_event("القط", exposure_id=102, event_order=0).core_event
    ev_b102 = encode_lexical_token_event("يشرب", exposure_id=102, event_order=1).core_event

    state_b.W.stable_bindings[z_cell] = dataclasses.replace(
        state_b.W.stable_bindings[z_cell],
        l_z_q6=100_000,
        u_z_q6=500_000,
    )
    tx_b = ExposureTransactionManager(state_b, allow_headless_events=True)
    tx_b.begin_exposure(102)
    tx_b.process_event(ev_a102)
    tx_b.process_event(ev_b102)
    report_b = tx_b.end_exposure(102)

    assert report_b.status == ExposureStatus.COMPLETED
    assert StatusCode.INVALID_CONTEXT_THRESHOLD in report_b.diagnostics
    assert state_b.W.stable_bindings[z_cell].status == BindingStatus.STALE, "Committed exposure failed to settle invalid binding to STALE!"


# ===========================================================================
# 2. Focused Latent Neighborhood Virtual Lookup Tests
# ===========================================================================

def test_latent_lookup_on_unmaterialized_cell():
    """Verify get_slots_read_only returns deterministic 24 slots without inserting into _slots_by_cell."""
    table = LatentNeighborhoodTable()
    unmaterialized_id = 3500
    assert unmaterialized_id not in table._slots_by_cell

    # Call get_slots_read_only
    slots_ro = table.get_slots_read_only(unmaterialized_id)
    assert len(slots_ro) == 24
    assert unmaterialized_id not in table._slots_by_cell, "Read-only lookup mutated _slots_by_cell!"

    # Call get_slots (should delegate to get_slots_read_only)
    slots_delegated = table.get_slots(unmaterialized_id)
    assert slots_delegated == slots_ro
    assert unmaterialized_id not in table._slots_by_cell, "get_slots mutated _slots_by_cell!"

    # Verify fixed slots
    expected_local = compute_fixed_local_neighbors(unmaterialized_id)
    expected_topo = compute_fixed_topographic_neighbors(unmaterialized_id)
    assert slots_ro[6:12] == expected_local
    assert slots_ro[18:24] == expected_topo
    assert all(slots_ro[i] is None for i in range(0, 6))
    assert all(slots_ro[i] is None for i in range(12, 18))


def test_virtual_vs_materialized_neighbor_equality():
    """Verify virtual neighbor computation matches explicit materialize_cell output exactly."""
    table = LatentNeighborhoodTable()
    cell_id = 7777

    slots_virtual = table.get_slots_read_only(cell_id)
    assert cell_id not in table._slots_by_cell

    slots_materialized = tuple(table.materialize_cell(cell_id))
    assert cell_id in table._slots_by_cell
    assert slots_virtual == slots_materialized


def test_reverse_neighbors_and_eligibility_immutability():
    """Verify reverse_neighbors and is_eligible do not mutate _slots_by_cell for candidate sources."""
    table = LatentNeighborhoodTable()
    src = 500
    tgt = 501

    assert src not in table._slots_by_cell
    assert tgt not in table._slots_by_cell

    # Reverse neighbors check
    rev = table.reverse_neighbors(tgt)
    assert isinstance(rev, set)
    assert len(table._slots_by_cell) == 0, "reverse_neighbors mutated _slots_by_cell!"

    # Eligibility check
    eligible = table.is_eligible(src, tgt)
    assert isinstance(eligible, bool)
    assert len(table._slots_by_cell) == 0, "is_eligible mutated _slots_by_cell!"


# ===========================================================================
# 3. Focused GENERATE Immutability and Ledger Tests
# ===========================================================================

def test_generate_episode_caller_state_and_ledger_immutability():
    """Verify generate_episode leaves caller permanent state and readout ledger 100% untouched."""
    state, ev_a, ev_b, _ = _build_rich_test_state()
    ledger = SurfaceReadoutLedgerV1()

    # Pre-snapshots
    w_snap_before = snapshot_w(state.W)
    h_snap_before = snapshot_h_slow(state.H_slow)
    r_snap_before = snapshot_r(state.R)
    ledger_snap_before = snapshot_ledger(ledger)

    # Run generate_episode
    gen_summary = generate_episode(
        state,
        [ev_a, ev_b],
        ledger,
        max_steps=3,
    )

    # Post-snapshots
    assert snapshot_w(state.W) == w_snap_before, "WState mutated during GENERATE_EPISODE!"
    assert snapshot_h_slow(state.H_slow) == h_snap_before, "HSlowState mutated during GENERATE_EPISODE!"
    assert snapshot_r(state.R) == r_snap_before, "RState mutated during GENERATE_EPISODE!"
    assert snapshot_ledger(ledger) == ledger_snap_before, "Readout ledger mutated during GENERATE_EPISODE!"


# ===========================================================================
# 4. Mode Discrimination for last_referenced_event
# ===========================================================================

def test_learn_mode_updates_last_referenced_event_while_retrieve_does_not():
    """Verify LEARN mode updates last_referenced_event for active cells while RETRIEVE never updates it."""
    state, ev_a, ev_b, _ = _build_rich_test_state()
    p_a = project_core_event_v1(ev_a)
    active_cell = next(iter(p_a.x_fixed_by_global_id.keys()))

    # Set clock to 50
    state.W.global_event_clock = 50
    state.W.last_referenced_event[active_cell] = 10

    # 1. Execute in RETRIEVE mode
    proj = project_core_event_v1(ev_a)
    execute_two_pass_event(
        state,
        proj.x_fixed_by_global_id,
        proj.x_float_by_global_id,
        mode=ExecutionMode.RETRIEVE,
        origin=EventOrigin.READ_ONLY_OBSERVED,
        boundary=True,
    )
    assert state.W.last_referenced_event[active_cell] == 10, "last_referenced_event updated in RETRIEVE mode!"

    # 2. Execute in LEARN mode
    execute_two_pass_event(
        state,
        proj.x_fixed_by_global_id,
        proj.x_float_by_global_id,
        mode=ExecutionMode.LEARN,
        origin=EventOrigin.EXTERNAL_DIRECT,
        boundary=True,
    )
    assert state.W.last_referenced_event[active_cell] == 50, "last_referenced_event NOT updated in LEARN mode!"
